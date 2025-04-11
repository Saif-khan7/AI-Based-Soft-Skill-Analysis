// src/pages/AnswerAssessment.js
import React, { useState, useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';

function AnswerAssessment() {
  const { user } = useUser();
  const location = useLocation();
  const navigate = useNavigate();

  const [assessmentData, setAssessmentData] = useState(null);

  useEffect(() => {
    const fetchAssessment = async() => {
      if (!user?.primaryEmailAddress) {
        console.warn("No user email - not fetching assessment");
        return;
      }
      const interviewId = location.state?.interviewId;
      if (!interviewId) {
        console.warn("No interviewId in route state. Can't fetch assessment.");
        return;
      }
      try {
        const res = await fetch("http://localhost:5000/api/getAssessment", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Clerk-User-Email": user.primaryEmailAddress.emailAddress
          },
          body: JSON.stringify({ interviewId })
        });
        const data = await res.json();
        if (data.error) {
          console.error("Assessment error:", data.error);
        } else {
          setAssessmentData(data);
        }
      } catch(err) {
        console.error("fetchAssessment error:", err);
      }
    };
    fetchAssessment();
  }, [user, location.state]);

  if (!assessmentData) {
    return <div style={{ textAlign:'center', marginTop:'50px'}}>
      <h2>Loading Q&A Assessment...</h2>
    </div>;
  }

  const { questions, answers } = assessmentData;

  const handleProceed = () => {
    // Navigate to the final summary + chart page
    navigate("/analysis", { state: { interviewId: location.state.interviewId } });
  };

  return (
    <div style={{ textAlign:'center', marginTop:'30px' }}>
      <h2>Answer Assessment</h2>
      <p>Below are your questions, transcripts, and ratings from the LLM:</p>

      <div style={{ maxWidth:'600px', margin:'20px auto', textAlign:'left' }}>
        {questions.map((q, idx) => {
          const ans = answers.find(a => a.questionIndex === idx);
          return (
            <div key={idx} style={{ marginBottom:'20px'}}>
              <p><strong>Q{idx+1}:</strong> {q}</p>
              {ans ? (
                <div style={{ marginLeft:'20px'}}>
                  <p><strong>Transcript:</strong> {ans.transcript}</p>
                  {ans.assessment && (
                    <>
                      <p><strong>Rating:</strong> {ans.assessment.rating}</p>
                      <p><strong>Explanation:</strong> {ans.assessment.explanation}</p>
                      <p><strong>Ideal Answer:</strong> {ans.assessment.ideal_answer}</p>
                    </>
                  )}
                </div>
              ) : (
                <p style={{ color:'red', marginLeft:'20px'}}>
                  No answer recorded
                </p>
              )}
            </div>
          );
        })}
      </div>

      <button onClick={handleProceed} style={{ padding:'10px 20px', cursor:'pointer' }}>
        View Final Summary & Chart
      </button>
    </div>
  );
}

export default AnswerAssessment;
