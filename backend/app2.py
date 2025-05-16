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

NUM_TECH_Q = 2 
# ---------------------------------------------------
# Load environment variables
# ---------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", None)
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set. Check your .env file.")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db = client["soft-skill"]

# Collections
resume_collection = db["resume"]
questions_collection = db["questions"]  # still optional
interviews_collection = db["interviews"]
soft_skill_coll = db["softSkillQuestions"]  # must match your actual collection name

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

    wpm = total_words / total_minutes if total_minutes>0 else 0.0
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
    transcript = result.get("text","")
    detected_lang = result.get("language","unknown")
    metrics = compute_speech_metrics(result)
    return detected_lang.upper(), transcript, metrics

# ---------------------------------------------------
# Helper to remove code fences from Gemini output
# ---------------------------------------------------
def remove_code_fences(gemini_text: str) -> str:
    return gemini_text.replace("```json", "").replace("```", "").strip()

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
# 4) Resume Analysis Endpoint (unchanged)
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
# 6) Start Interview => 5 technical + 6 soft skill Qs
# ---------------------------------------------------
@app.route("/api/startInterview", methods=["POST"])
def start_interview():
    """
    1) Summarize the resume's key_skills if missing
    2) Generate 5 skill-based (technical) Qs from Gemini
    3) Fetch 1 random question from each of the 6 soft skill sections in softSkillQuestions:
       communication, teamwork, problemSolving, adaptability, leadership, timeManagement
    4) Merge them -> final questions (total 11)
    5) Create interview doc
    """
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    last_resume = resume_collection.find_one({"email": clerk_email}, sort=[("created_at", -1)])
    if not last_resume:
        return jsonify({"error": "No resume found; please upload resume first"}), 400

    if not gemini_model:
        return jsonify({"error": "Gemini model not loaded"}), 500

    # Summarize if needed
    skills_summary = last_resume.get("skills_summary", "").strip()
    if not skills_summary:
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

    # 1) Generate the 5 skill-based (technical) Qs from the resume skills
    lines = []
    for ln in skills_summary.split("\n"):
        sk = ln.strip("-").strip()
        if sk:
            lines.append(sk)
    lines = list(dict.fromkeys(lines))[:10]
    bullet_list = "\n".join([f"- {s}" for s in lines])

    tech_prompt = f"""
Below is the candidate's skill list (ignore any mention of lacking skill):
{bullet_list}

Generate exactly {NUM_TECH_Q} skill-based interview questions.
Each question must mention at least two distinct skill names from above 
and ask how the candidate has used them in real projects.

Return only a valid JSON array of {NUM_TECH_Q} strings, with no extra commentary or metadata.
If you cannot comply, return "Unable to comply."
"""

    def call_model(p):
        try:
            r = gemini_model.generate_content(p)
            text_out = r.text if (r and r.text) else "[]"
            return remove_code_fences(text_out)
        except Exception as e:
            return f"Error calling model: {e}"

    raw_output = call_model(tech_prompt)

    def parse_json_arr(txt):
        try:
            arr = json.loads(txt)
            if not isinstance(arr, list):
                return [txt]
            return arr
        except:
            return [txt]

    skill_questions = parse_json_arr(raw_output)

    # optional check each question references 2+ skill names
    def skill_count_in_q(q):
        q_lower = q.lower()
        found = []
        for sk in lines:
            if sk.lower() in q_lower:
                found.append(sk)
        return len(set(found))

    all_ok = True
    for q in skill_questions:
        if skill_count_in_q(q) < 2:
            all_ok = False
            break
    if not all_ok:
        raw2 = call_model(tech_prompt)
        skill_questions = parse_json_arr(raw2)

    # 2) 6 soft-skill sections to pick from the DB: communication, teamwork, etc.
    sections = ["communication", "teamwork", "problemSolving", "adaptability", "leadership", "timeManagement"]
    soft_skill_questions = []
    import random
    for section in sections:
        doc = db["softSkillQuestions"].find_one({"section": section})
        if doc and doc.get("questions"):
            qlist = doc["questions"]
            chosen = random.choice(qlist)
            soft_skill_questions.append(chosen)
        else:
            soft_skill_questions.append(f"[Missing question for {section}]")

    # Combine final list: 5 technical + 6 soft skill => 11 total
    final_questions = skill_questions + soft_skill_questions

    interview_doc = {
        "email": clerk_email,
        "questions": final_questions,
        "answers": [],
        "emotionTimeline": [],
        "status": "in_progress",
        "created_at": datetime.utcnow(),
        "technicalCount": NUM_TECH_Q ,
        "softSkillCount": 6,  # next 6 are soft skill Qs
        "softSkillSections": sections
    }
    res = interviews_collection.insert_one(interview_doc)

    return jsonify({
        "message": "Interview started with skill-based + 6 soft-skill questions",
        "interviewId": str(res.inserted_id),
        "questions": final_questions
    })

# ---------------------------------------------------
# 7) /api/submitAnswer => Transcribe, store, LLM rating
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

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    try:
        # save and transcribe audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        lang, transcript, metrics = transcribe_audio(tmp_path)

        old_len = len(interview.get("answers", []))
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
        interviews_collection.update_one(
            {"_id": obj_id},
            {"$push": {"answers": answer_doc}}
        )

        # Optional: call LLM to assess the answer with rating, explanation, ideal answer.
        assessment = {}
        try:
            if gemini_model:
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
                assessment = {"rating": 3, "explanation": "Gemini not loaded", "ideal_answer": ""}
        except Exception as e:
            assessment = {"rating": 3, "explanation": f"Error: {str(e)}", "ideal_answer": ""}

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

# ---------------------------------------------------
# 8) finalizeInterview => mark as completed
# ---------------------------------------------------
@app.route("/api/finalizeInterview", methods=["POST"])
def finalize_interview():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}),401

    data = request.json
    interview_id = data.get("interviewId")
    if not interview_id:
        return jsonify({"error":"Missing interviewId"}),400

    try:
        obj_id = ObjectId(interview_id)
    except:
        return jsonify({"error":"Invalid interviewId"}),400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error":"Interview not found"}),404

    interviews_collection.update_one(
        {"_id": obj_id},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.utcnow()
        }}
    )
    return jsonify({"message":"Interview finalized"})

# ---------------------------------------------------
# 9) /api/getAnalysis  – speech stats + skill bullets + emotion insight
# ---------------------------------------------------
@app.route("/api/getAnalysis", methods=["POST"])
def get_analysis():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email:
        return jsonify({"error": "Not authenticated"}), 401

    interview_id = (request.json or {}).get("interviewId")
    if not interview_id:
        return jsonify({"error": "Missing interviewId"}), 400
    try:
        obj_id = ObjectId(interview_id)
    except Exception:
        return jsonify({"error": "Invalid interviewId"}), 400

    interview = interviews_collection.find_one({"_id": obj_id, "email": clerk_email})
    if not interview:
        return jsonify({"error": "Interview not found"}), 404

    answers          = interview.get("answers", [])
    emotion_timeline = interview.get("emotionTimeline", [])
    status           = interview.get("status", "in_progress")
    completed_at     = interview.get("completed_at")

    # ---------- speech metrics ------------------------------------------------
    total_words  = sum(len(a.get("transcript", "").split()) for a in answers)
    total_filler = sum(a.get("fillerCount", 0) for a in answers)
    ratings      = [a["assessment"]["rating"]
                    for a in answers
                    if isinstance(a.get("assessment"), dict) and "rating" in a["assessment"]]

    avg_rating  = round(sum(ratings) / len(ratings), 2) if ratings else 3.0
    filler_rate = round(total_filler / total_words, 3) if total_words else 0.0

    # ---------- emotion statistics -------------------------------------------
    import statistics
    buckets = {}
    for snap in emotion_timeline:
        for emo, val in (snap.get("distribution") or {}).items():
            buckets.setdefault(emo, []).append(float(val))

    emo_avg = {e: round(sum(v) / len(v), 1)
               for e, v in buckets.items()} if buckets else {}
    emo_std = {e: round(statistics.pstdev(v), 1)
               for e, v in buckets.items() if len(v) > 1}

    def top_k(d, k=2):
        return ", ".join(f"{e} ({v}%)"
                         for e, v in sorted(d.items(), key=lambda x: x[1], reverse=True)[:k])

    emotion_digest = ("No emotion captured."
                      if not emo_avg
                      else f"Dominant → {top_k(emo_avg)} | Most variable → {top_k(emo_std)}")

    # ---------- per-skill bullet analysis (unchanged) -------------------------
    skill_order = interview.get("softSkillSections",
        ["communication","teamwork","problemSolving","adaptability","leadership","timeManagement"])
    skillAnalysis = {}
    if gemini_model:
        for i, skill in enumerate(skill_order):
            q_idx = 5 + i
            ans   = next((a for a in answers if a["questionIndex"] == q_idx), None)
            if not ans:
                skillAnalysis[skill] = f"No answer provided for {skill}."
                continue
            transcript = ans.get("transcript", "")
            rating     = ans.get("assessment", {}).get("rating", 3)

            prompt = f"""
You are evaluating the candidate's {skill} skill.
Transcript:
\"\"\"{transcript}\"\"\"
Numeric rating: {rating}/5.
Give up to 5 bullet-points (strengths / weaknesses)."""
            try:
                txt = gemini_model.generate_content(prompt).text or ""
                skillAnalysis[skill] = remove_code_fences(txt)
            except Exception as e:
                skillAnalysis[skill] = f"Error: {e}"
    else:
        skillAnalysis = {s: "Gemini not loaded." for s in skill_order}

    # ---------- final natural-language summary & emotion bullets -------------
    final_summary   = "Gemini not loaded"
    emotion_bullets = []

    if gemini_model:
        try:
            summary_prompt = f"""
You are an interview evaluator.

Speech metrics → rating {avg_rating}/5, filler {filler_rate}, words {total_words}.
Emotions → {emotion_digest}

Interpretation rules:
- A predominantly *neutral* face (e.g., >60 %) usually signals calm composure, **not** disengagement.
- A predominantly *happy* or *surprise* face indicates enthusiasm / positive engagement.
- Anger, sadness, fear or disgust in high proportions may indicate stress or negativity.

Write 3–4 sentences assessing communication, confidence and engagement,
using BOTH speech and emotion evidence.  No code fences."""
            final_summary = gemini_model.generate_content(summary_prompt).text.strip()
        except Exception as e:
            final_summary = f"(Could not generate summary – {e})"

        try:
            bullet_prompt = f"""
Given these average facial-emotion percentages:
{json.dumps(emo_avg, indent=2)}

Using the same interpretation rules as above (neutral = calm,
happy/surprise = enthusiastic),
list up to 4 concise bullet points on engagement, stress level and authenticity.
No code fences."""
            raw = gemini_model.generate_content(bullet_prompt).text or ""
            emotion_bullets = [l.lstrip("•- ").strip() for l in raw.splitlines() if l.strip()]
        except Exception:
            emotion_bullets = ["Could not analyse emotions via LLM."]

    # ---------- response ------------------------------------------------------
    return jsonify({
        "status": status,
        "completed_at": completed_at,
        "emotionTimeline": emotion_timeline,
        "emotionAverages": emo_avg,
        "emotionStd": emo_std,
        "emotionAnalysis": emotion_bullets,
        "avgRating": avg_rating,
        "fillerRate": filler_rate,
        "totalWordsSpoken": total_words,
        "final_summary": final_summary,
        "skillAnalysis": skillAnalysis
    })



# ---------------------------------------------------
# 10) getAssessment => Q & A details for AnswerAssessment page
# ---------------------------------------------------
@app.route("/api/getAssessment", methods=["POST"])
def get_assessment():
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

    return jsonify({
        "questions": interview.get("questions", []),
        "answers": interview.get("answers", []),
        "status": interview.get("status", "in_progress"),
        "completed_at": interview.get("completed_at", None)
    })

if __name__ == "__main__":
    app.run(debug=True)
