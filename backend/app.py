import os
import re
import cv2
import base64
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set. Check your .env file.")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client['softskill_interviews']  # Database name

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)
try:
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    print("Error loading Gemini model:", e)
    gemini_model = None

app = Flask(__name__)
CORS(app)

# ---------------------------
# 1) Whisper Model Setup
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
# DeepFace Frame Analysis
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
# Resume Analysis and Skill Extraction
# ---------------------------
@app.route("/api/resume", methods=["POST"])
def analyze_resume():
    """
    Expects a form-data field 'resumeFile' (PDF or DOCX) and an optional 'jobDescription'.
    1. Extract text from the file.
    2. Construct a Gemini prompt that asks the AI to output a structured JSON:
         - full_name, contact_details, professional_summary,
         - relevant_experience, key_skills, certifications, industry_expertise.
       If a job description is provided, also include a match_score (0-10) and a brief explanation.
    3. Return the Gemini output as 'analysis'.
    """
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

        # Construct prompt (structured JSON output)
        if job_description:
            prompt = f"""
You are an HR assistant analyzing a resume for a specific job.
Extract and output the following details in JSON format:
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
Extract and output the following details in JSON format:
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

        if not gemini_model:
            return jsonify({"analysis": "Gemini model not loaded or unavailable."}), 200

        try:
            response = gemini_model.generate_content(prompt)
            gemini_output = response.text if response and response.text else "No response from Gemini."
        except Exception as e:
            gemini_output = f"Error analyzing resume with Gemini: {e}"

        return jsonify({"analysis": gemini_output})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"analysis": f"Error: {e}"}), 200
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# Helper: Extract text from PDF
def extract_text_from_pdf(pdf_path):
    text_content = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text_content += page.extract_text() or ""
    return text_content.strip()

# Helper: Extract text from DOCX
def extract_text_from_docx(docx_path):
    return docx2txt.process(docx_path).strip()

if __name__ == '__main__':
    app.run(debug=True)
