import os, re, cv2, base64, json, numpy as np, tempfile, traceback
from collections import Counter
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv; load_dotenv()

import PyPDF2, docx2txt, google.generativeai as genai
from deepface import DeepFace
import whisper, requests
from pymongo import MongoClient
from bson.objectid import ObjectId

NUM_TECH_Q = 2            # default fallback

# ─────────────────────────── DB & Gemini init ──────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MONGO_URI      = os.getenv("MONGO_URI","mongodb://localhost:27017")

client = MongoClient(MONGO_URI)
db     = client["soft-skill"]

resume_collection      = db["resume"]
interviews_collection  = db["interviews"]

genai.configure(api_key=GEMINI_API_KEY)
try:
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
except Exception as e:
    print("Gemini load error:", e); gemini_model = None

app = Flask(__name__); CORS(app)

# ─────────────────────────── Whisper helpers ───────────────────────────────
whisper_model = whisper.load_model("base")
FILLER_WORDS  = {"um","uh","like","you","know","er","ah","so","well","actually"}

def compute_speech_metrics(res):
    seg  = res.get("segments",[])
    if not seg: return dict(wpm=0,filler_rate=0,filler_count=0,filler_words_used={})
    tot_time   = seg[-1]["end"]-seg[0]["start"]
    words      = re.findall(r"\w+"," ".join(s["text"] for s in seg).lower())
    wpm        = len(words)/(tot_time/60) if tot_time else 0
    fillers    = Counter(w for w in words if w in FILLER_WORDS)
    return dict(
        wpm           = wpm,
        filler_rate   = sum(fillers.values())/len(words) if words else 0,
        filler_count  = sum(fillers.values()),
        filler_words_used = dict(fillers)
    )

def transcribe_audio(path):
    res = whisper_model.transcribe(path, language=None)
    return res.get("language","UNK").upper(), res.get("text",""), compute_speech_metrics(res)

def remove_code_fences(t): return t.replace("```json","").replace("```","").strip()

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
# 7) /api/submitAnswer  ← ★ UPDATED BLOCK INSIDE ★
# ---------------------------------------------------
@app.route("/api/submitAnswer", methods=["POST"])
def submit_answer():
    clerk_email  = request.headers.get("Clerk-User-Email")
    if not clerk_email:  return jsonify({"error":"Not authenticated"}),401

    interview_id = request.form.get("interviewId")
    q_idx        = int(request.form.get("questionIndex","0"))
    if not interview_id:           return jsonify({"error":"Missing interviewId"}),400
    if "audio" not in request.files:return jsonify({"error":"No audio file"}),400

    obj_id   = ObjectId(interview_id)
    interview= interviews_collection.find_one({"_id":obj_id,"email":clerk_email})
    if not interview:              return jsonify({"error":"Interview not found"}),404

    tmp_path = None
    try:
        # -- save audio temp
        with tempfile.NamedTemporaryFile(delete=False,suffix=".wav") as tmp:
            request.files["audio"].save(tmp.name)
            tmp_path = tmp.name

        lang, transcript, metrics = transcribe_audio(tmp_path)

        # -- push raw answer
        ans_doc = dict(
            questionIndex   = q_idx,
            transcript      = transcript,
            language        = lang,
            wpm             = metrics["wpm"],
            fillerRate      = metrics["filler_rate"],
            fillerCount     = metrics["filler_count"],
            fillerWordsUsed = metrics["filler_words_used"],
            timestamp       = datetime.utcnow()
        )
        interviews_collection.update_one({"_id":obj_id},{"$push":{"answers":ans_doc}})
        answer_pos = len(interview.get("answers",[]))  # position after push

        # -- LLM assessment --------------------------------------------------
        assessment = {}
        if gemini_model:
            tech_cnt = interview.get("technicalCount", NUM_TECH_Q)
            is_soft  = q_idx >= tech_cnt
            q_text   = interview["questions"][q_idx] if q_idx < len(interview["questions"]) else ""

            if is_soft:
                prompt = f"""
You are a behavioural-interview assessor.

Return JSON:
{{
  "rating":       1-5,
  "strengths":    [string],   // ≤5
  "improvements": [string]    // ≤5
}}

Question: {q_text}
Answer transcript: {transcript}
"""
            else:
                prompt = f"""
You are a technical interviewer.

Return JSON:
{{
  "rating":       1-5,
  "explanation":  string,
  "ideal_answer": string
}}

Question: {q_text}
Answer transcript: {transcript}
"""

            try:
                raw = remove_code_fences(gemini_model.generate_content(prompt).text or "{}")
                print("Gemini raw:", raw)                           # debug line
                try:
                    parsed = json.loads(raw) if raw.strip().startswith("{") else {}
                except:
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}

                if is_soft:
                    # Always include placeholders for explanation/ideal
                    assessment = {
                        "rating"      : parsed.get("rating", 3),
                        "strengths"   : parsed.get("strengths", []),
                        "improvements": parsed.get("improvements", []),
                        "explanation" : "Explanation not applicable",
                        "ideal_answer": "Ideal answer not applicable"
                    }
                else:
                    assessment = {
                        "rating"      : parsed.get("rating", 3),
                        "explanation" : parsed.get("explanation", "Explanation not available"),
                        "ideal_answer": parsed.get("ideal_answer", "Ideal answer not available"),
                        # keep empty arrays for UI consistency
                        "strengths"   : [],
                        "improvements": []
                    }

            except Exception as e:
                assessment = {
                    "rating"      : 3,
                    "explanation" : f"Parse error: {e}",
                    "ideal_answer": "N/A",
                    "strengths"   : [],
                    "improvements": []
                }

        # -- store assessment
        interviews_collection.update_one(
            {"_id":obj_id},
            {"$set":{f"answers.{answer_pos}.assessment":assessment}}
        )

        return jsonify({"message":"Answer submitted",
                        "metrics":metrics,
                        "assessment":assessment})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error":str(e)}),500
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
# 9) /api/getAnalysis — UPDATED
# ---------------------------------------------------
@app.route("/api/getAnalysis", methods=["POST"])
def get_analysis():
    clerk_email = request.headers.get("Clerk-User-Email")
    if not clerk_email: return jsonify({"error":"Not authenticated"}),401

    iid = (request.json or {}).get("interviewId")
    if not iid: return jsonify({"error":"Missing interviewId"}),400
    try: obj_id = ObjectId(iid)
    except: return jsonify({"error":"Invalid interviewId"}),400

    interview = interviews_collection.find_one({"_id":obj_id,"email":clerk_email})
    if not interview: return jsonify({"error":"Interview not found"}),404

    answers       = interview.get("answers",[])
    emo_timeline  = interview.get("emotionTimeline",[])
    tech_cnt      = interview.get("technicalCount", NUM_TECH_Q)      ##### <NEW>

    # ----- speech stats -------------------------------------------------------
    tot_words  = sum(len(a.get("transcript","").split()) for a in answers)
    tot_filler = sum(a.get("fillerCount",0) for a in answers)
    ratings    = [a.get("assessment",{}).get("rating",3) for a in answers if a.get("assessment")]
    avg_rating = round(sum(ratings)/len(ratings),2) if ratings else 3.0
    filler_rt  = round(tot_filler/tot_words,3) if tot_words else 0.0

    # ----- emotion aggregate (unchanged) --------------------------------------
    import statistics
    bucket={}
    for snap in emo_timeline:
        for emo,v in (snap.get("distribution") or {}).items():
            bucket.setdefault(emo,[]).append(float(v))
    emo_avg = {e:round(sum(v)/len(v),1) for e,v in bucket.items()}
    emo_std = {e:round(statistics.pstdev(v),1) for e,v in bucket.items() if len(v)>1}

    # ----- per-skill analysis --------------------------------------------------
    skill_sections = interview.get("softSkillSections",
        ["communication","teamwork","problemSolving","adaptability","leadership","timeManagement"])
    skillAnalysis  = {}
    if gemini_model:
        for i,skill in enumerate(skill_sections):
            q_idx = tech_cnt + i                                     ##### <NEW>
            ans   = next((a for a in answers if a["questionIndex"]==q_idx),None)
            if not ans:
                skillAnalysis[skill]="No answer provided."
                continue
            tr   = ans.get("transcript","")
            rat  = ans.get("assessment",{}).get("rating",3)
            try:
                txt = gemini_model.generate_content(
f"""Evaluate {skill}.
Transcript: \"\"\"{tr}\"\"\" Rating:{rat}/5.
Give ≤5 bullet points.""").text
                skillAnalysis[skill]=remove_code_fences(txt)
            except Exception as e:
                skillAnalysis[skill]=f"Error: {e}"
    else:
        skillAnalysis = {s:"Gemini not loaded." for s in skill_sections}

    # ----- final summary & emotion bullets (same code as before) --------------
    top = lambda d,k=2:", ".join(f"{e} ({v}%)" for e,v in sorted(d.items(),key=lambda x:x[1],reverse=True)[:k])
    emo_digest = "No emotion captured." if not emo_avg else f"Dominant → {top(emo_avg)} | Var → {top(emo_std)}"
    final_summary="Gemini not loaded"; emo_bullets=[]
    if gemini_model:
        try:
            final_summary = gemini_model.generate_content(
f"""Speech rating {avg_rating}, filler {filler_rt}, words {tot_words}. Emotions: {emo_digest}.
Neutral = calm, happy/surprise = enthusiastic.
Write 3–4 sentence assessment.""").text.strip()
            raw = gemini_model.generate_content(
f"Avg emotions: {json.dumps(emo_avg)}. Give ≤4 bullets on engagement/stress.").text
            emo_bullets=[l.lstrip("•- ").strip() for l in raw.splitlines() if l.strip()]
        except: pass

    return jsonify(dict(
        status          = interview.get("status"),
        completed_at    = interview.get("completed_at"),
        emotionTimeline = emo_timeline,
        emotionAverages = emo_avg,
        emotionStd      = emo_std,
        emotionAnalysis = emo_bullets,
        avgRating       = avg_rating,
        fillerRate      = filler_rt,
        totalWordsSpoken= tot_words,
        final_summary   = final_summary,
        skillAnalysis   = skillAnalysis
    ))



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
