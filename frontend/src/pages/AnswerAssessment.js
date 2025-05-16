import React, { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useUser } from "@clerk/clerk-react";

function AnswerAssessment() {
  const { user } = useUser();
  const location = useLocation();
  const navigate = useNavigate();
  const [assessmentData, setAssessmentData] = useState(null);

  /* ─────────── fetch unchanged ─────────── */
  useEffect(() => {
    const fetchAssessment = async () => {
      if (!user?.primaryEmailAddress) return;
      const interviewId = location.state?.interviewId;
      if (!interviewId) return;
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
        if (!data.error) setAssessmentData(data);
      } catch (err) {
        console.error("fetchAssessment error:", err);
      }
    };
    fetchAssessment();
  }, [user, location.state]);

  const handleProceed = () =>
    navigate("/analysis", { state: { interviewId: location.state?.interviewId } });

  if (!assessmentData)
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <h1 style={styles.headerTitle}>Loading Assessment...</h1>
        </div>
        <div style={{ textAlign: "center", marginTop: 50 }}>
          <h2>Please wait while we fetch your results.</h2>
        </div>
      </div>
    );

  const { questions, answers } = assessmentData;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.headerTitle}>Answer Assessment</h1>
        <p style={styles.headerSubtitle}>
          Here are your recorded answers and the LLM-based analysis.
        </p>
      </div>

      <div style={styles.content}>
        <div style={styles.assessmentList}>
          {questions.map((q, idx) => {
            const ans = answers.find((a) => a.questionIndex === idx);
            const a   = ans?.assessment || {};
            const isSoft = a.strengths && a.strengths.length;
            return (
              <div key={idx} style={styles.qCard}>
                <h2 style={styles.qTitle}>Question {idx + 1}</h2>
                <p style={styles.questionText}>{q}</p>

                {ans ? (
                  <div style={styles.answerContainer}>
                    <p style={styles.answerLine}>
                      <strong>Transcript:</strong> {ans.transcript || "No transcript"}
                    </p>
                    <p style={styles.answerLine}>
                      <strong>Rating:</strong> {a.rating ?? "N/A"}
                    </p>

                    {isSoft ? (
                      <>
                        <p style={styles.answerLine}>
                          <strong>Strengths:</strong>
                        </p>
                        <ul>
                          {(a.strengths || []).map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                        <p style={styles.answerLine}>
                          <strong>Improvements:</strong>
                        </p>
                        <ul>
                          {(a.improvements || []).map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </>
                    ) : (
                      <>
                        <p style={styles.answerLine}>
                          <strong>Explanation:</strong>{" "}
                          {a.explanation || "Explanation not available"}
                        </p>
                        <p style={styles.answerLine}>
                          <strong>Ideal Answer:</strong>{" "}
                          {a.ideal_answer || "Ideal answer not available"}
                        </p>
                      </>
                    )}
                  </div>
                ) : (
                  <p style={styles.noAnswer}>No answer recorded</p>
                )}
              </div>
            );
          })}
        </div>

        <div style={styles.buttonArea}>
          <button style={styles.proceedButton} onClick={handleProceed}>
            View Final Summary &amp; Chart
          </button>
        </div>
      </div>
    </div>
  );
}
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
