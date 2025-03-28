import os
import re
import cv2
import base64
import json
import numpy as np
import tempfile
import traceback
from collections import Counter
from datetime import datetime

from flask import Flask, request, jsonify
from flask_cors import CORS

# For environment variables
from dotenv import load_dotenv
load_dotenv()

# For resume parsing
import PyPDF2
import docx2txt

# For Gemini API
import google.generativeai as genai

# For DeepFace and Whisper
from deepface import DeepFace
import whisper
import requests

# For MongoDB Atlas
from pymongo import MongoClient

# ---------------------------------------------------
# Load environment variables
# ---------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set. Check your .env file.")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["soft-skill"]              # database name
resume_collection = db["resume"]       # existing collection for resume analysis
questions_collection = db["questions"] # new collection for interview questions

# Test the MongoDB connection
try:
    client.admin.command("ping")
    print("Successfully connected to MongoDB Atlas!")
except Exception as e:
    print("Could not connect to MongoDB Atlas:", e)

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
try:
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    print("Error loading Gemini model:", e)
    gemini_model = None

app = Flask(__name__)
CORS(app)

# ---------------------------
# 1) Whisper Setup
# ---------------------------
whisper_model = whisper.load_model("base")
FILLER_WORDS = {"um", "uh", "like", "you", "know", "er", "ah", "so", "well", "actually"}

def compute_speech_metrics(transcription_result):
    segments = transcription_result.get("segments", [])
    if not segments:
        return {"wpm": 0.0, "filler_rate": 0.0, "filler_count": 0, "filler_words_used": {}}

    total_speaking_time = segments[-1]["end"] - segments[0]["start"]
    if total_speaking_time <= 0:
        return {"wpm": 0.0, "filler_rate": 0.0, "filler_count": 0, "filler_words_used": {}}

    full_text = " ".join(s["text"] for s in segments)
    words = re.findall(r"\w+", full_text.lower())
    total_words = len(words)
    total_minutes = total_speaking_time / 60.0

    wpm = total_words / total_minutes if total_minutes else 0.0
    filler_counter = Counter(w for w in words if w in FILLER_WORDS)
    filler_count = sum(filler_counter.values())
    filler_rate = filler_count / total_words if total_words else 0.0

    return {
        "wpm": wpm,
        "filler_rate": filler_rate,
        "filler_count": filler_count,
        "filler_words_used": dict(filler_counter)
    }

def transcribe_audio(audio_file_path):
    result = whisper_model.transcribe(audio_file_path, language=None)
    transcript = result.get("text", "")
    detected_lang = result.get("language", "unknown")
    metrics = compute_speech_metrics(result)
    return detected_lang.upper(), transcript, metrics

@app.route("/processAudio", methods=["POST"])
def process_audio():
    if "audio" not in request.files:
        return jsonify({"error": "No audio file provided"}), 400

    audio_file = request.files["audio"]
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        lang, transcript, metrics = transcribe_audio(tmp_path)
        return jsonify({
            "language": lang,
            "transcript": transcript,
            "speechRateWPM": round(metrics["wpm"], 2),
            "fillerRate": round(metrics["filler_rate"], 3),
            "fillerCount": metrics["filler_count"],
            "fillerWordsUsed": metrics["filler_words_used"]
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# ---------------------------
# 2) DeepFace Frame Analysis
# ---------------------------
@app.route('/analyzeFrame', methods=['POST'])
def analyze_frame():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'error': 'No image data'}), 400

    try:
        encoded_image = data['image'].split(',')[1]
        np_arr = np.frombuffer(base64.b64decode(encoded_image), np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'error': 'Invalid image data'}), 400

        analysis = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
        if isinstance(analysis, list) and len(analysis) > 0:
            face_data = analysis[0]
        else:
            face_data = analysis

        dominant_emotion = face_data.get('dominant_emotion', 'unknown')
        region = face_data.get('region', {})

        if region:
            x, y = region.get('x', 0), region.get('y', 0)
            w, h = region.get('w', 0), region.get('h', 0)
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)
            cv2.putText(
                img,
                dominant_emotion,
                (x, y - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.9,
                (255, 0, 0),
                2
            )

        _, buffer = cv2.imencode('.jpg', img)
        processed_base64 = base64.b64encode(buffer).decode('utf-8')
        processed_image = f"data:image/jpeg;base64,{processed_base64}"

        return jsonify({
            'emotion': dominant_emotion,
            'image': processed_image
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ---------------------------
# 3) Resume Analysis Endpoint
# ---------------------------
@app.route("/api/resume", methods=["POST"])
def analyze_resume():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"analysis": "User not authenticated."}), 401

    if "resumeFile" not in request.files:
        return jsonify({"analysis": "No resume file provided."}), 200

    resume_file = request.files["resumeFile"]
    job_description = request.form.get("jobDescription", "").strip()
    tmp_path = None

    try:
        file_ext = resume_file.filename.split(".")[-1].lower()
        if file_ext not in ["pdf", "docx"]:
            return jsonify({"analysis": "Unsupported file type. Please upload PDF or DOCX."}), 200

        suffix = f".{file_ext}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            resume_file.save(tmp.name)
            tmp_path = tmp.name

        if file_ext == "pdf":
            resume_text = extract_text_from_pdf(tmp_path)
        else:
            resume_text = extract_text_from_docx(tmp_path)

        if not resume_text.strip():
            return jsonify({"analysis": "No text could be extracted from the resume."}), 200

        if not gemini_model:
            return jsonify({"analysis": "Gemini model not loaded or unavailable."}), 200

        # Build prompt
        if job_description:
            prompt = f"""
You are an HR assistant analyzing a resume for a specific job.
Extract the following details in a structured JSON:
{{
  "full_name": string,
  "contact_details": string,
  "professional_summary": string,
  "relevant_experience": string,
  "key_skills": string,
  "certifications": string,
  "industry_expertise": string,
  "match_score": number,
  "match_explanation": string
}}

Resume Text:
{resume_text}

Job Description:
{job_description}
"""
        else:
            prompt = f"""
You are an HR assistant analyzing a resume.
Extract the following details in a structured JSON:
{{
  "full_name": string,
  "contact_details": string,
  "professional_summary": string,
  "relevant_experience": string,
  "key_skills": string,
  "certifications": string,
  "industry_expertise": string
}}

Resume Text:
{resume_text}
"""

        # Call Gemini
        try:
            response = gemini_model.generate_content(prompt)
            gemini_output = response.text if response and response.text else "No response from Gemini."
        except Exception as e:
            gemini_output = f"Error analyzing resume with Gemini: {e}"

        # Store doc
        resume_doc = {
            "email": clerk_email,
            "analysis": gemini_output,
            "job_description": job_description,
            "resume_text": resume_text[:1000],
            "created_at": datetime.utcnow()
        }
        resume_collection.insert_one(resume_doc)

        return jsonify({"analysis": gemini_output})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"analysis": f"Error: {e}"}), 200
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# ---------------------------
# 4) Question Generation Endpoint
# ---------------------------
@app.route("/api/generateQuestions", methods=["POST"])
def generate_questions():
    """
    1) Retrieves the user's email from the headers.
    2) Finds the user's most recent resume doc in 'resume' collection.
    3) Extracts 'key_skills' from the JSON analysis.
    4) Calls Gemini to generate an array of interview questions.
    5) Stores them in a 'questions' collection (with references to the user).
    6) Returns the generated questions.
    """
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "User not authenticated."}), 401

    # Find the user's last resume doc. Sort by created_at desc, pick first
    last_resume = resume_collection.find_one(
        {"email": clerk_email},
        sort=[("created_at", -1)]
    )
    if not last_resume:
        return jsonify({"error": "No resume found for this user."}), 404

    analysis_json_str = last_resume.get("analysis", "")
    if not analysis_json_str:
        return jsonify({"error": "Analysis missing."}), 400

    # Attempt to parse the JSON structure from gemini_output
    # The gemini_output might be raw text, so we do a naive parse or a fallback
    try:
        # If Gemini's analysis is strictly JSON, parse it
        analysis_data = json.loads(analysis_json_str)
    except Exception:
        # If it's not valid JSON, fallback to entire text
        analysis_data = {}
    
    # We'll pull key_skills from analysis_data["key_skills"], if present
    key_skills = analysis_data.get("key_skills", "")
    if not key_skills:
        # fallback: parse the text to see if there's a "key_skills" field
        key_skills = "No identified skills."

    if not gemini_model:
        return jsonify({"error": "Gemini model not loaded"}), 500

    # Build prompt to generate questions
    # Example: "Given these skills: X, generate 5 relevant interview questions..."
    prompt = f"""
You are a career coach. The candidate's key skills are: {key_skills}.
Generate 5 in-depth interview questions that specifically assess these skills.
Return only a JSON array, like: ["Question 1", "Question 2", ...].
"""

    try:
        response = gemini_model.generate_content(prompt)
        questions_output = response.text if response and response.text else "[]"
    except Exception as e:
        questions_output = f"Error generating questions: {e}"

    # Attempt to parse the questions JSON array
    try:
        generated_questions = json.loads(questions_output)
        if not isinstance(generated_questions, list):
            # If not a list, wrap it in a list
            generated_questions = [questions_output]
    except Exception:
        # If not valid JSON, fallback to entire string
        generated_questions = [questions_output]

    # Store them in the "questions" collection
    questions_doc = {
        "email": clerk_email,
        "resume_id": str(last_resume["_id"]),  # reference the resume doc
        "questions": generated_questions,
        "created_at": datetime.utcnow()
    }
    questions_collection.insert_one(questions_doc)

    return jsonify({"questions": generated_questions})

# Helpers for PDF/DOCX extraction
def extract_text_from_pdf(pdf_path):
    text_content = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text_content += page.extract_text() or ""
    return text_content.strip()

def extract_text_from_docx(docx_path):
    return docx2txt.process(docx_path).strip()

if __name__ == '__main__':
    app.run(debug=True)
