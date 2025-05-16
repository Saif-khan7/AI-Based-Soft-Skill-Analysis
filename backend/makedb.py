# makedb.py
import os
import sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()  # explicitly load the .env file

MONGO_URI = os.environ.get("MONGO_URI")  # read from the environment
if not MONGO_URI:
    print("MONGO_URI not found in environment!")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client["soft-skill"]
soft_skill_coll = db["softSkillQuestions"]


# Insert or update each section
sections_data = [
    {
      "section": "communication",
      "questions": [
        "Can you describe a time when you had to explain a complex idea to someone unfamiliar with it? How did you ensure clarity?",
        "Tell me about a situation where you had to communicate disappointing news to a client or colleague. How did you handle it?",
        "Share an example of how you adapted your communication style to suit different audiences or stakeholders.",
        "Describe a time when you had to persuade others to accept your point of view. What approach did you use?"
      ]
    },
    {
      "section": "teamwork",
      "questions": [
        "Give an example of when you worked successfully on a team project. What was your role, and what made the team effective?",
        "Describe a time you and a coworker had a disagreement. How did you address it to maintain a productive relationship?",
        "Tell me about a team goal that you helped to achieve. How did you contribute to the outcome?",
        "Explain a situation where you had to collaborate with diverse personalities or different departments. How did you align everyone toward a common goal?"
      ]
    },
    {
      "section": "problemSolving",
      "questions": [
        "Tell me about a challenging problem you faced and how you approached solving it. What was unique about your solution?",
        "Describe a situation where you anticipated a potential issue and took proactive steps to prevent it. What was the result?",
        "Share an example of a time you had limited resources but still had to deliver results. How did you adapt your problem-solving approach?",
        "Can you think of a time when you had multiple possible solutions? How did you evaluate and select the best one?"
      ]
    },
    {
      "section": "adaptability",
      "questions": [
        "Describe a time you had to adapt quickly to a significant organizational or technological change. How did you manage it?",
        "Tell me about a moment when your responsibilities changed unexpectedly. How did you handle the shift?",
        "Explain a scenario where you learned a new skill or process under tight deadlines. How did you ensure success?",
        "Give an example of how you’ve handled feedback or criticism that required you to alter your usual way of doing things."
      ]
    },
    {
      "section": "leadership",
      "questions": [
        "Give an example of when you took initiative to lead a project or a team. What motivated you to step up?",
        "Describe a situation where you had to motivate or inspire others to achieve a goal. What methods did you use?",
        "Tell me about a time you dealt with a team member’s poor performance. How did you handle it and what was the outcome?",
        "Explain how you balance giving direction with empowering your team members to take ownership."
      ]
    },
    {
      "section": "timeManagement",
      "questions": [
        "How do you prioritize tasks when you have multiple deadlines? Provide a specific example of how you managed it.",
        "Tell me about a situation where your schedule was unexpectedly disrupted. How did you maintain productivity?",
        "Describe a time you struggled with time management. What did you learn, and how do you manage your time differently now?",
        "Explain a scenario where you had competing priorities and limited resources. How did you ensure each task was completed on time?"
      ]
    }
]

for doc in sections_data:
    soft_skill_coll.update_one(
        {"section": doc["section"]},
        {"$set": {"questions": doc["questions"]}},
        upsert=True
    )

print("Soft skill questions inserted/updated!")
