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

from dotenv import load_dotenv
load_dotenv()

import PyPDF2
import docx2txt
import google.generativeai as genai
from deepface import DeepFace
import whisper
import requests
from pymongo import MongoClient
from bson.objectid import ObjectId

# ---------------------------------------------------
# Load environment variables
# ---------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set. Check your .env file.")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["soft-skill"]

resume_collection = db["resume"]
questions_collection = db["questions"]
interviews_collection = db["interviews"]

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)
try:
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    print("Error loading Gemini model:", e)
    gemini_model = None

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------
# Whisper Setup
# ---------------------------------------------------
whisper_model = whisper.load_model("base")
FILLER_WORDS = {"um","uh","like","you","know","er","ah","so","well","actually"}

def compute_speech_metrics(transcription_result):
    segments = transcription_result.get("segments", [])
    if not segments:
        return {
            "wpm": 0.0,
            "filler_rate": 0.0,
            "filler_count": 0,
            "filler_words_used": {}
        }

    total_speaking_time = segments[-1]["end"] - segments[0]["start"]
    if total_speaking_time <= 0:
        return {
            "wpm": 0.0,
            "filler_rate": 0.0,
            "filler_count": 0,
            "filler_words_used": {}
        }

    full_text = " ".join(s["text"] for s in segments)
    words = re.findall(r"\w+", full_text.lower())
    total_words = len(words)
    total_minutes = total_speaking_time / 60.0

    wpm = total_words / total_minutes if total_minutes > 0 else 0.0
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

# ---------------------------------------------------
# 1) Audio Endpoint
# ---------------------------------------------------
@app.route("/processAudio", methods=["POST"])
def process_audio():
    if "audio" not in request.files:
        return jsonify({"error":"No audio file provided"}),400

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

# ---------------------------------------------------
# 2) Frame Analysis (DeepFace)
# ---------------------------------------------------
@app.route('/analyzeFrame', methods=['POST'])
def analyze_frame():
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'error':'No image data'}),400

    try:
        encoded_image = data['image'].split(',')[1]
        np_arr = np.frombuffer(base64.b64decode(encoded_image), np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'error':'Invalid image data'}),400

        analysis = DeepFace.analyze(img, actions=['emotion'], enforce_detection=False)
        face_data = analysis[0] if isinstance(analysis, list) else analysis

        dominant_emotion = face_data.get('dominant_emotion','unknown')
        emotion_distribution = face_data.get('emotion',{})

        region = face_data.get('region',{})
        if region:
            x, y = region.get('x',0), region.get('y',0)
            w, h = region.get('w',0), region.get('h',0)
            cv2.rectangle(img,(x,y),(x+w,y+h),(255,0,0),2)
            cv2.putText(img, dominant_emotion,(x,y-10),
                        cv2.FONT_HERSHEY_SIMPLEX,0.9,(255,0,0),2)

        _, buffer = cv2.imencode('.jpg', img)
        processed_base64 = base64.b64encode(buffer).decode('utf-8')
        processed_image = f"data:image/jpeg;base64,{processed_base64}"

        return jsonify({
            'dominant_emotion': dominant_emotion,
            'emotion_distribution': emotion_distribution,
            'image': processed_image
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error':str(e)}),500

# ---------------------------------------------------
# 3) Log Emotion to Timeline
# ---------------------------------------------------
@app.route("/api/logEmotion", methods=["POST"])
def log_emotion():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error":"Not authenticated"}),401

    data = request.json
    interview_id = data.get("interviewId")
    if not interview_id:
        return jsonify({"error":"Missing interviewId"}),400

    distribution = data.get("emotion_distribution",{})
    if not isinstance(distribution, dict) or not distribution:
        return jsonify({"error":"No valid emotion distribution"}),400

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error":"Invalid interviewId"}),400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error":"Interview not found"}),404

    timeline_doc = {
        "timestamp": datetime.utcnow(),
        "distribution": distribution
    }
    interviews_collection.update_one(
        {"_id": obj_id},
        {"$push":{"emotionTimeline": timeline_doc}}
    )
    return jsonify({"message":"Emotion logged"})

# ---------------------------------------------------
# Helper: remove code fences from Gemini output
# ---------------------------------------------------
def remove_code_fences(gemini_text: str) -> str:
    cleaned = gemini_text.replace("```json", "").replace("```", "").strip()
    return cleaned

# ---------------------------------------------------
# 4) Resume Analysis Endpoint
# ---------------------------------------------------
def extract_text_from_pdf(pdf_path):
    text_content = ""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            text_content += page.extract_text() or ""
    return text_content.strip()

def extract_text_from_docx(docx_path):
    return docx2txt.process(docx_path).strip()

@app.route("/api/resume", methods=["POST"])
def analyze_resume():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"analysis":"User not authenticated."}),401

    if "resumeFile" not in request.files:
        return jsonify({"analysis":"No resume file provided."}),200

    resume_file = request.files["resumeFile"]
    job_description = request.form.get("jobDescription","").strip()

    tmp_path = None
    try:
        file_ext = resume_file.filename.split(".")[-1].lower()
        if file_ext not in ["pdf","docx"]:
            return jsonify({"analysis":"Unsupported file type. Please upload PDF or DOCX."}),200

        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_ext}") as tmp:
            resume_file.save(tmp.name)
            tmp_path = tmp.name

        if file_ext == "pdf":
            resume_text = extract_text_from_pdf(tmp_path)
        else:
            resume_text = extract_text_from_docx(tmp_path)

        if not resume_text.strip():
            return jsonify({"analysis":"No text could be extracted from the resume."}),200

        if not gemini_model:
            return jsonify({"analysis":"Gemini model not loaded or unavailable."}),200

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
You are an HR assistant analyzing a resume (no job description).
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

        try:
            response = gemini_model.generate_content(prompt)
            gemini_output = response.text if response and response.text else "No response from Gemini."
            gemini_output = remove_code_fences(gemini_output)
        except Exception as e:
            gemini_output = f"Error analyzing resume with Gemini: {e}"

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
        return jsonify({"analysis":str(e)}),200
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

# ---------------------------------------------------
# 5) Summarize Key Skills
# ---------------------------------------------------
@app.route("/api/extractSkills", methods=["POST"])
def extract_skills():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    last_resume = resume_collection.find_one({"email": clerk_email}, sort=[("created_at", -1)])
    if not last_resume:
        return jsonify({"error": "No resume found"}), 404

    analysis_json = last_resume.get("analysis", "")
    if not analysis_json:
        return jsonify({"error": "No analysis found"}), 400

    try:
        data = json.loads(analysis_json)
    except:
        data = {}

    raw_skills = data.get("key_skills", "")
    if not raw_skills.strip():
        return jsonify({"error": "No key_skills found in analysis"}), 400

    if not gemini_model:
        return jsonify({"error": "Gemini model not loaded"}), 500

    cleaned = re.sub(r"(Languages|Tools|Technologies/Frameworks):", "", raw_skills, flags=re.IGNORECASE)
    prompt = f"""
We have these raw skill lines from a resume:
\"\"\"{cleaned}\"\"\"

Ignore any mention that the candidate lacks skills.
Produce a SHORT bullet list (max 10) of distinct skill names.
No explanation, no code fences, just bullet items.
"""
    try:
        resp = gemini_model.generate_content(prompt)
        summary_text = resp.text if (resp and resp.text) else "- No Skills"
        summary_text = remove_code_fences(summary_text)
    except Exception as e:
        summary_text = f"Error summarizing skills: {e}"

    resume_collection.update_one(
        {"_id": last_resume["_id"]},
        {"$set": {"skills_summary": summary_text}}
    )

    return jsonify({"skills_summary": summary_text})

# ---------------------------------------------------
# 6) Start Interview => Generate skill-based Q's
# ---------------------------------------------------
@app.route("/api/startInterview", methods=["POST"])
def start_interview():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    last_resume = resume_collection.find_one({"email": clerk_email}, sort=[("created_at", -1)])
    if not last_resume:
        return jsonify({"error": "No resume found; please upload resume first"}), 400

    if not gemini_model:
        return jsonify({"error": "Gemini model not loaded"}), 500

    skills_summary = last_resume.get("skills_summary", "").strip()

    if not skills_summary:
        # Summarize automatically if missing
        analysis_json = last_resume.get("analysis", "")
        if not analysis_json:
            return jsonify({"error": "No analysis found. Please upload resume first."}), 400
        try:
            data = json.loads(analysis_json)
        except:
            data = {}
        raw_skills = data.get("key_skills", "")
        if not raw_skills.strip():
            return jsonify({"error": "No key_skills found in analysis"}), 400

        cleaned = re.sub(r"(Languages|Tools|Technologies/Frameworks):", "", raw_skills, flags=re.IGNORECASE)
        sum_prompt = f"""
We have these raw skill lines from a resume:
\"\"\"{cleaned}\"\"\"

Ignore any mention that the candidate lacks skills.
Produce a SHORT bullet list (max 10) of distinct skill names.
No explanation, no code fences, just bullet items.
"""
        try:
            resp = gemini_model.generate_content(sum_prompt)
            summary_text = resp.text if (resp and resp.text) else "- No Skills"
            summary_text = remove_code_fences(summary_text)
        except Exception as e:
            summary_text = f"Error summarizing skills: {e}"

        resume_collection.update_one(
            {"_id": last_resume["_id"]},
            {"$set": {"skills_summary": summary_text}}
        )
        skills_summary = summary_text

    if not skills_summary or skills_summary.lower().startswith("error"):
        return jsonify({"error": "Failed to summarize skills automatically."}), 400

    lines = []
    for ln in skills_summary.split("\n"):
        skill = ln.strip("-").strip()
        if skill:
            lines.append(skill)
    lines = list(dict.fromkeys(lines))[:10]

    bullet_list = "\n".join([f"- {s}" for s in lines])

    gen_prompt = f"""
Below is the candidate's skill list (ignore any mention of lacking skill):
{bullet_list}

Generate exactly 5 skill-based interview questions.
Each question must mention at least two distinct skill names from above 
and ask how the candidate has used them in real projects.

Return only a valid JSON array of 5 strings, with no extra commentary or metadata.
If you cannot comply, return "Unable to comply."
"""

    def call_model(p):
        try:
            r = gemini_model.generate_content(p)
            text_out = r.text if (r and r.text) else "[]"
            return remove_code_fences(text_out)
        except Exception as e:
            return f"Error calling model: {e}"

    raw_output = call_model(gen_prompt)

    def parse_json_arr(txt):
        try:
            arr = json.loads(txt)
            if not isinstance(arr, list):
                return [txt]
            return arr
        except:
            return [txt]

    questions = parse_json_arr(raw_output)

    def skill_count_in_q(q):
        q_lower = q.lower()
        found = []
        for sk in lines:
            if sk.lower() in q_lower:
                found.append(sk)
        return len(set(found))

    # If not all have 2+ skills, try once more
    all_ok = True
    for q in questions:
        if skill_count_in_q(q) < 2:
            all_ok = False
            break
    if not all_ok:
        raw_output2 = call_model(gen_prompt)
        questions = parse_json_arr(raw_output2)

    interview_doc = {
        "email": clerk_email,
        "questions": questions,
        "answers": [],
        "emotionTimeline": [],
        "status": "in_progress",
        "created_at": datetime.utcnow()
    }
    res = interviews_collection.insert_one(interview_doc)

    return jsonify({
        "message": "Interview started with skill-based questions",
        "interviewId": str(res.inserted_id),
        "questions": questions
    })

# ---------------------------------------------------
# 7) Submit Answer (with Gemini-based assessment), Finalize, getAnalysis
# ---------------------------------------------------
@app.route("/api/submitAnswer", methods=["POST"])
def submit_answer():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    interview_id = request.form.get("interviewId")
    question_idx_str = request.form.get("questionIndex", "0")
    try:
        question_idx = int(question_idx_str)
    except:
        question_idx = 0

    if not interview_id:
        return jsonify({"error": "Missing interviewId"}), 400
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400

    audio_file = request.files["audio"]
    tmp_path = None

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error": "Invalid interviewId"}), 400

    # 1) Find interview
    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    try:
        # 2) Save and transcribe
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        lang, transcript, metrics = transcribe_audio(tmp_path)

        # 3) Insert the new answer doc
        answer_doc = {
            "questionIndex": question_idx,
            "transcript": transcript,
            "language": lang,
            "wpm": metrics["wpm"],
            "fillerRate": metrics["filler_rate"],
            "fillerCount": metrics["filler_count"],
            "fillerWordsUsed": metrics["filler_words_used"],
            "timestamp": datetime.utcnow()
        }

        old_len = len(interview.get("answers", []))
        # push the doc
        interviews_collection.update_one(
            {"_id": obj_id},
            {"$push": {"answers": answer_doc}}
        )

        # 4) Optionally call Gemini to assess the answer
        # We'll store the rating, explanation, ideal_answer in "assessment"
        assessment = {}
        try:
            if gemini_model:
                # get question text
                question_text = ""
                if 0 <= question_idx < len(interview["questions"]):
                    question_text = interview["questions"][question_idx]

                prompt = f"""
You are an expert interviewer. 
Rate the user's answer on a scale of 1 to 5 (5=excellent). 
Provide a short explanation and a short 'ideal answer' summary. 
Return only valid JSON:
{{
  "rating": integer,
  "explanation": string,
  "ideal_answer": string
}}

Question: {question_text}
User's Answer Transcript: {transcript}
"""
                resp = gemini_model.generate_content(prompt)
                raw = resp.text if (resp and resp.text) else "{}"
                raw = remove_code_fences(raw)
                try:
                    parsed = json.loads(raw)
                    if not isinstance(parsed, dict):
                        parsed = {"rating": 3, "explanation": "Parsing error", "ideal_answer": "N/A"}
                    assessment = parsed
                except:
                    assessment = {"rating": 3, "explanation": raw[:200], "ideal_answer": "No parse"}
            else:
                assessment = {"rating": 3, "explanation": "Gemini model not loaded", "ideal_answer": ""}
        except Exception as e:
            assessment = {"rating": 3, "explanation": f"Error: {str(e)}", "ideal_answer": ""}

        # 5) Update that newly inserted answer with the assessment
        # We'll re-fetch the interview or just do array indexing
        interviews_collection.update_one(
            {"_id": obj_id},
            {"$set": {f"answers.{old_len}.assessment": assessment}}
        )

        return jsonify({
            "message": "Answer submitted",
            "transcript": transcript,
            "metrics": metrics,
            "assessment": assessment
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

@app.route("/api/finalizeInterview", methods=["POST"])
def finalize_interview():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    interview_id = data.get("interviewId")
    if not interview_id:
        return jsonify({"error": "Missing interviewId"}), 400

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error": "Invalid interviewId"}), 400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    interviews_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.utcnow()
        }}
    )
    return jsonify({"message": "Interview finalized"})

@app.route("/api/getAnalysis", methods=["POST"])
def get_analysis():
    """
    Returns final summary (LLM-based) + emotion timeline
    We do NOT return the question/answer details here 
    because that's in /api/getAssessment now.
    """
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    interview_id = data.get("interviewId")
    if not interview_id:
        return jsonify({"error": "Missing interviewId"}), 400

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error": "Invalid interviewId"}), 400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    # We'll gather stats: average filler rate, average rating, etc.
    answers = interview.get("answers", [])
    emotion_timeline = interview.get("emotionTimeline", [])
    # final user status
    status = interview.get("status", "in_progress")
    completed_at = interview.get("completed_at", None)

    # let's compute filler usage, average rating
    total_filler = 0
    total_words = 0
    count_answered = 0
    total_rating = 0
    rating_count = 0

    for ans in answers:
        count_answered += 1
        if ans.get("fillerCount"):
            total_filler += ans["fillerCount"]
        # You might approximate total words from transcript's word count or use wpm
        if ans.get("transcript"):
            word_count = len(ans["transcript"].split())
            total_words += word_count

        # rating from gemini
        assessment = ans.get("assessment")
        if assessment and isinstance(assessment, dict):
            r = assessment.get("rating")
            if r and isinstance(r, int):
                total_rating += r
                rating_count += 1

    avg_rating = total_rating / rating_count if rating_count else 3
    overall_filler_rate = float(total_filler)/float(total_words) if total_words>0 else 0.0

    # We'll call Gemini to create a final summary about:
    # - communication
    # - confidence
    # - overall soft skills
    final_summary = ""
    try:
        if gemini_model:
            # Build a prompt referencing these stats
            prompt = f"""
You are an evaluator of soft skills. 
We have an interview with the following stats:
- # of answers: {count_answered}
- average rating: {avg_rating:.2f} (1..5 scale)
- filler rate: {overall_filler_rate:.3f} 
- total words spoken: {total_words}

The user wants a final summary of their communication skills, confidence level, 
and general soft skills, referencing the rating and filler usage. 
Return only a short textual summary (no code blocks).
"""
            resp = gemini_model.generate_content(prompt)
            final_summary = resp.text if resp and resp.text else ""
        else:
            final_summary = "Gemini model not loaded"
    except Exception as e:
        final_summary = f"Error generating final summary: {str(e)}"

    # Return final summary + emotion timeline data
    return jsonify({
        "status": status,
        "completed_at": completed_at,
        "final_summary": final_summary,
        "emotionTimeline": emotion_timeline
    })


@app.route("/api/getAssessment", methods=["POST"])
def get_assessment():
    """
    Returns the interview's questions + answers (with Gemini-based rating), 
    but NOT the final summary or emotion data.
    This is for the 'AnswerAssessment' page.
    """
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json
    interview_id = data.get("interviewId")
    if not interview_id:
        return jsonify({"error": "Missing interviewId"}), 400

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error": "Invalid interviewId"}), 400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    # We only return questions + answers (with any assessment)
    return jsonify({
        "questions": interview.get("questions", []),
        "answers": interview.get("answers", []),
        "status": interview.get("status", "in_progress"),
        "completed_at": interview.get("completed_at", None)
    })


if __name__ == "__main__":
    app.run(debug=True)
