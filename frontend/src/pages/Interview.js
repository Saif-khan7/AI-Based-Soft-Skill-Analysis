// src/pages/Interview.js
import React, { useState, useRef, useEffect } from 'react';
import { useUser } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';

function Interview() {
  const navigate = useNavigate();
  const { user } = useUser();

  const videoRef = useRef(null);
  const captureIntervalRef = useRef(null);

  const [stream, setStream] = useState(null);
  const [emotion, setEmotion] = useState("");
  const [processedImage, setProcessedImage] = useState(null);
  const [isCapturing, setIsCapturing] = useState(false);

  const [interviewId, setInterviewId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [currentQIndex, setCurrentQIndex] = useState(0);

  const [audioRecorder, setAudioRecorder] = useState(null);
  const [isRecording, setIsRecording] = useState(false);

  useEffect(() => {
    return () => {
      stopVideo();
      stopCapturing();
      if (audioRecorder) audioRecorder.stop();
    };
    // eslint-disable-next-line
  }, []);

  // ----------------------
  // 1) Start Interview => calls /api/startInterview
  // ----------------------
  const handleStartInterview = async () => {
    if (!user?.primaryEmailAddress) {
      alert("Please sign in first");
      return;
    }
    try {
      const res = await fetch("http://localhost:5000/api/startInterview", {
        method: "POST",
        headers: {
          "Clerk-User-Email": user.primaryEmailAddress.emailAddress
        }
      });
      const data = await res.json();
      if (data.interviewId) {
        setInterviewId(data.interviewId);
        if (Array.isArray(data.questions)) {
          setQuestions(data.questions);
        } else {
          setQuestions([data.questions]);
        }
        setCurrentQIndex(0);
      } else {
        alert(data.error || "Failed to start interview");
      }
    } catch (err) {
      console.error("Error starting interview:", err);
      alert("Interview error");
    }
  };

  // ----------------------
  // 2) Video & Emotion Tracking
  // ----------------------
  const startVideo = async () => {
    try {
      const userStream = await navigator.mediaDevices.getUserMedia({ video: true });
      setStream(userStream);
      if (videoRef.current) {
        videoRef.current.srcObject = userStream;
        videoRef.current.play();
      }
    } catch (err) {
      console.error("Video error:", err);
    }
  };

  const stopVideo = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }
    setStream(null);
  };

  const startCapturing = () => {
    setIsCapturing(true);
    captureIntervalRef.current = setInterval(() => captureFrame(), 2000);
  };

  const stopCapturing = () => {
    setIsCapturing(false);
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
  };

  const captureFrame = async() => {
    if (!videoRef.current) return;
    const canvas = document.createElement("canvas");
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
    const base64Image = canvas.toDataURL("image/jpeg");

    try {
      const resp = await fetch("http://localhost:5000/analyzeFrame", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ image: base64Image })
      });
      const data = await resp.json();

      if (!data.error) {
        setEmotion(data.dominant_emotion);
        setProcessedImage(data.image);

        if (interviewId && user?.primaryEmailAddress && data.emotion_distribution) {
          await fetch("http://localhost:5000/api/logEmotion", {
            method:"POST",
            headers: {
              "Content-Type":"application/json",
              "Clerk-User-Email": user.primaryEmailAddress.emailAddress
            },
            body: JSON.stringify({
              interviewId,
              emotion_distribution: data.emotion_distribution
            })
          });
        }
      }
    } catch(e) { 
      console.error("Emotion error:", e);
    }
  };

  // ----------------------
  // 3) Audio => /api/submitAnswer
  // ----------------------
  const handleStartRecording = async() => {
    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(audioStream);
      const chunks = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size>0) chunks.push(e.data);
      };
      recorder.onstop = async() => {
        const audioBlob = new Blob(chunks, { type:"audio/wav" });
        const formData = new FormData();
        formData.append("audio", audioBlob,"answer.wav");
        formData.append("interviewId", interviewId);
        formData.append("questionIndex", currentQIndex.toString());

        try {
          const res = await fetch("http://localhost:5000/api/submitAnswer", {
            method:"POST",
            headers:{
              "Clerk-User-Email": user.primaryEmailAddress.emailAddress
            },
            body: formData
          });
          const data = await res.json();
          if (data.message === "Answer submitted") {
            alert("Answer recorded successfully!");
            if (data.assessment) {
              alert(`Rating: ${data.assessment.rating}\nExplanation: ${data.assessment.explanation}\nIdeal Answer: ${data.assessment.ideal_answer}`);
            }
          } else {
            alert(data.error || "Error submitting answer");
          }
        } catch(err) {
          console.error("submitAnswer error:", err);
        }
      };

      recorder.start();
      setAudioRecorder(recorder);
      setIsRecording(true);
    } catch(err) {
      console.error("Mic error:", err);
      alert("Could not access microphone.");
    }
  };

  const handleStopRecording = () => {
    if (audioRecorder) {
      audioRecorder.stop();
      audioRecorder.stream.getTracks().forEach(t=>t.stop());
    }
    setIsRecording(false);
    setAudioRecorder(null);
  };

  // ----------------------
  // 4) Next / Finish Interview
  // ----------------------
  const handleNextQuestion = () => {
    if (currentQIndex < questions.length - 1) {
      setCurrentQIndex(currentQIndex + 1);
    } else {
      alert("You are on the final question. You can finish now.");
    }
  };

  const handleFinishInterview = async() => {
    if (!interviewId) {
      alert("No interview in progress to finalize!");
      return;
    }
    try {
      const res = await fetch("http://localhost:5000/api/finalizeInterview", {
        method:"POST",
        headers:{
          "Content-Type":"application/json",
          "Clerk-User-Email": user.primaryEmailAddress.emailAddress
        },
        body: JSON.stringify({ interviewId })
      });
      const data = await res.json();
      if (data.message === "Interview finalized") {
        navigate("/answerAssessment", { state: { interviewId }} );
      } else {
        alert(data.error || "Error finalizing interview");
      }
    } catch(err) {
      console.error("Finalize error:", err);
      alert("Could not finalize interview.");
    }
  };

  const renderQuestion = (qItem) => {
    if (!qItem) return null;
    if (typeof qItem === "string") {
      return <p>{qItem}</p>;
    } else if (typeof qItem === "object") {
      return (
        <div>
          <p style={{ fontWeight: 600, marginBottom: '0.3rem' }}>{qItem.question}</p>
          {qItem.skill_tested && (
            <p style={{ fontSize: '0.9rem', color: '#666' }}>
              <em>Skills: {qItem.skill_tested}</em>
            </p>
          )}
        </div>
      );
    } else {
      return <p>{String(qItem)}</p>;
    }
  };

  // ----------------------
  // Styles
  // ----------------------
  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    fontFamily: 'Poppins, sans-serif',
    minHeight: '100vh'
  };

  const headerStyle = {
    textAlign: 'center',
    padding: '2rem 1rem',
    background: 'linear-gradient(135deg, #6EE2F5 0%, #6454F0 100%)',
    color: '#fff',
    marginBottom: '2rem'
  };

  const headingStyle = {
    margin: 0,
    fontWeight: 600
  };

  const subHeadingStyle = {
    marginTop: '0.5rem',
    opacity: 0.9
  };

  // The main content has 2 columns: left = video/emotion, right = Q&A
  // We set alignItems:'flex-start' so they don't stretch to equal heights
  const contentStyle = {
    display: 'flex',
    gap: '2rem',
    padding: '0 2rem',
    flexWrap: 'wrap',              // on small screens, it wraps
    justifyContent: 'center',
    alignItems: 'flex-start'       // no forced equal height
  };

  const cardStyle = {
    background: '#fff',
    borderRadius: '8px',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    padding: '1.5rem',
    marginBottom: '2rem'
  };

  // We'll define a fixed or min width so each card doesn't match height
  const videoCardStyle = {
    ...cardStyle,
    flex: '0 0 450px',  // does not grow beyond 450
    maxWidth: '500px'
  };

  const qACardStyle = {
    ...cardStyle,
    flex: '0 0 450px',
    maxWidth: '500px'
  };

  const cardTitleStyle = {
    marginTop: 0,
    marginBottom: '1rem',
    fontWeight: 600,
    fontSize: '1.2rem'
  };

  const buttonStyle = {
    padding: '0.6rem 1.2rem',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontFamily: 'Poppins, sans-serif',
    fontWeight: 500,
    marginRight: '0.5rem'
  };

  const purpleButtonStyle = {
    ...buttonStyle,
    backgroundColor: '#6454F0',
    color: '#fff'
  };

  const grayButtonStyle = {
    ...buttonStyle,
    backgroundColor: '#f5f5f5',
    color: '#333'
  };

  const cameraButtonStyle = {
    ...purpleButtonStyle,
    marginBottom: '1rem'
  };

  return (
    <div style={containerStyle}>
      {/* Hero Header */}
      <div style={headerStyle}>
        <h1 style={headingStyle}>AI-Powered Interview</h1>
        <p style={subHeadingStyle}>Real-time emotion tracking & skill-based questions</p>
      </div>

      <div style={contentStyle}>
        {/* Left Column: Video & Emotion */}
        <div style={videoCardStyle}>
          <h2 style={cardTitleStyle}>Emotion Tracking</h2>

          {!stream ? (
            <button style={cameraButtonStyle} onClick={startVideo}>
              Start Camera
            </button>
          ) : (
            <button style={cameraButtonStyle} onClick={stopVideo}>
              Stop Camera
            </button>
          )}

          {!isCapturing && stream && (
            <button style={grayButtonStyle} onClick={startCapturing}>
              Start Emotion Tracking
            </button>
          )}
          {isCapturing && (
            <button style={grayButtonStyle} onClick={stopCapturing}>
              Stop Emotion Tracking
            </button>
          )}

          <div style={{ marginTop: '1rem', border: '1px solid #ccc', borderRadius: '4px', overflow: 'hidden' }}>
            <video 
              ref={videoRef} 
              style={{ width: '100%', display: stream ? 'block' : 'none' }}
            />
          </div>

          <p style={{ fontWeight: 500, marginTop: '0.75rem' }}>
            Current Emotion: <span style={{ color: '#6454F0' }}>{emotion}</span>
          </p>

          {processedImage && (
            <img
              src={processedImage}
              alt="Processed"
              style={{ width:'100%', marginTop:'10px', borderRadius:'4px' }}
            />
          )}
        </div>

        {/* Right Column: Q&A */}
        <div style={qACardStyle}>
          {!interviewId && (
            <div style={{ textAlign: 'center' }}>
              <h2 style={cardTitleStyle}>Ready to Begin?</h2>
              <p style={{ color: '#666', marginBottom: '1rem' }}>
                This will generate skill-based questions tailored to your resume.
              </p>
              <button style={purpleButtonStyle} onClick={handleStartInterview}>
                Start Interview
              </button>
            </div>
          )}

          {interviewId && (
            <>
              <p style={{ marginBottom: '1rem', color: '#888' }}>
                <strong>Interview ID:</strong> {interviewId}
              </p>

              {questions.length > 0 && currentQIndex < questions.length && (
                <div>
                  <h3 style={{ marginBottom: '0.5rem', fontWeight: 600 }}>
                    Question {currentQIndex + 1} of {questions.length}
                  </h3>
                  {renderQuestion(questions[currentQIndex])}

                  <div style={{ marginTop: '1rem' }}>
                    {!isRecording ? (
                      <button style={purpleButtonStyle} onClick={handleStartRecording}>
                        Record Answer
                      </button>
                    ) : (
                      <button style={purpleButtonStyle} onClick={handleStopRecording}>
                        Stop Recording
                      </button>
                    )}

                    {currentQIndex < questions.length - 1 ? (
                      <button 
                        style={{ ...grayButtonStyle, marginLeft: '0.5rem' }}
                        onClick={handleNextQuestion}
                      >
                        Next Question
                      </button>
                    ) : (
                      <p style={{ margin: '0.5rem 0', color: '#888', fontSize: '0.9rem' }}>
                        (Final Question)
                      </p>
                    )}
                  </div>
                </div>
              )}

              {currentQIndex >= questions.length - 1 && (
                <div style={{ marginTop: '1.5rem' }}>
                  <button style={purpleButtonStyle} onClick={handleFinishInterview}>
                    Finish Interview
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default Interview;