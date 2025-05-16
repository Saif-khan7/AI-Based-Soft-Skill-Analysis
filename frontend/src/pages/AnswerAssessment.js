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

  const handleProceed = () => {
    // Navigate to the final summary + chart page
    navigate("/analysis", { state: { interviewId: location.state?.interviewId } });
  };

  if (!assessmentData) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h1 style={styles.headerTitle}>Loading Assessment...</h1>
        </div>
        <div style={{ textAlign: 'center', marginTop: '50px' }}>
          <h2>Please wait while we fetch your results.</h2>
        </div>
      </div>
    );
  }

  const { questions, answers } = assessmentData;

  return (
    <div style={styles.container}>
      {/* Hero header */}
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Answer Assessment</h1>
        <p style={styles.headerSubtitle}>
          Here are your recorded answers and the LLM-based analysis.
        </p>
      </div>

      {/* Main content */}
      <div style={styles.content}>
        <div style={styles.assessmentList}>
          {questions.map((question, idx) => {
            const ans = answers.find(a => a.questionIndex === idx);
            return (
              <div key={idx} style={styles.qCard}>
                <h2 style={styles.qTitle}>Question {idx + 1}</h2>
                <p style={styles.questionText}>{question}</p>

                {ans ? (
                  <div style={styles.answerContainer}>
                    <p style={styles.answerLine}>
                      <strong>Transcript: </strong>
                      {ans.transcript}
                    </p>

                    {ans.assessment ? (
                      <>
                        <p style={styles.answerLine}>
                          <strong>Rating:</strong> {ans.assessment.rating}
                        </p>
                        <p style={styles.answerLine}>
                          <strong>Explanation:</strong> {ans.assessment.explanation}
                        </p>
                        <p style={styles.answerLine}>
                          <strong>Ideal Answer:</strong> {ans.assessment.ideal_answer}
                        </p>
                      </>
                    ) : (
                      <p style={styles.noAssessment}>No LLM assessment available.</p>
                    )}
                  </div>
                ) : (
                  <p style={styles.noAnswer}>
                    No answer recorded
                  </p>
                )}
              </div>
            );
          })}
        </div>

        <div style={styles.buttonArea}>
          <button style={styles.proceedButton} onClick={handleProceed}>
            View Final Summary & Chart
          </button>
        </div>
      </div>
    </div>
  );
}

// Inline styles for a consistent, modern look
const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    fontFamily: 'Poppins, sans-serif',
    minHeight: '100vh'
  },
  header: {
    padding: '2rem 1rem',
    background: 'linear-gradient(135deg, #6EE2F5 0%, #6454F0 100%)',
    textAlign: 'center',
    color: '#fff',
    marginBottom: '2rem'
  },
  headerTitle: {
    margin: 0,
    fontWeight: 600
  },
  headerSubtitle: {
    marginTop: '0.5rem',
    fontSize: '1rem',
    opacity: 0.9
  },
  content: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '0 1rem',
    flex: 1
  },
  assessmentList: {
    maxWidth: '700px',
    width: '100%'
  },
  qCard: {
    backgroundColor: '#fff',
    borderRadius: '8px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.12)',
    marginBottom: '1.5rem',
    padding: '1rem'
  },
  qTitle: {
    margin: 0,
    marginBottom: '0.5rem',
    fontWeight: 600,
    fontSize: '1.1rem',
    color: '#333'
  },
  questionText: {
    marginBottom: '1rem',
    fontSize: '0.95rem',
    color: '#444'
  },
  answerContainer: {
    marginLeft: '1rem'
  },
  answerLine: {
    marginBottom: '0.5rem',
    color: '#444'
  },
  noAssessment: {
    marginLeft: '1rem',
    color: '#999'
  },
  noAnswer: {
    marginLeft: '1rem',
    color: 'red'
  },
  buttonArea: {
    marginTop: '2rem',
    marginBottom: '2rem'
  },
  proceedButton: {
    padding: '0.8rem 1.5rem',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontFamily: 'Poppins, sans-serif',
    fontWeight: 500,
    backgroundColor: '#6454F0',
    color: '#fff',
    boxShadow: '0 2px 5px rgba(0,0,0,0.15)',
    fontSize: '1rem'
  }
};

export default AnswerAssessment;
