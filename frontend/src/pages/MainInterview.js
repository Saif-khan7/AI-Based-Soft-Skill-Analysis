import React, { useState, useRef, useEffect } from 'react';
import { useUser } from '@clerk/clerk-react';
import { useNavigate } from 'react-router-dom';

function MainInterview() {
  const navigate = useNavigate();
  const { user } = useUser();

  const videoRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [emotion, setEmotion] = useState("");
  const [processedImage, setProcessedImage] = useState(null);
  const captureIntervalRef = useRef(null);
  const [isCapturing, setIsCapturing] = useState(false);

  const [interviewId, setInterviewId] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [currentQIndex, setCurrentQIndex] = useState(0);

  const [audioRecorder, setAudioRecorder] = useState(null);
  const [isRecording, setIsRecording] = useState(false);

  useEffect(() => {
    // Cleanup
    return () => {
      stopVideo();
      stopCapturing();
      if (audioRecorder) audioRecorder.stop();
    };
    // eslint-disable-next-line
  }, []);

  // 1) Start the Interview
  const handleStartInterview = async() => {
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

        // data.questions is presumably an array: e.g. ["Q1","Q2","Q3","Q4","Q5"]
        setQuestions(Array.isArray(data.questions) ? data.questions : [data.questions]);
        setCurrentQIndex(0);
        alert("Interview started!");
      } else {
        alert(data.error || "Failed to start interview");
      }
    } catch (err) {
      console.error("Error starting interview:", err);
      alert("Interview error");
    }
  };

  // 2) Video & Emotion
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
    ctx.drawImage(videoRef.current,0,0, canvas.width,canvas.height);
    const base64Image = canvas.toDataURL("image/jpeg");

    try {
      // 1) Analyze emotion
      const resp = await fetch("http://localhost:5000/analyzeFrame", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({ image: base64Image })
      });
      const data = await resp.json();

      if (!data.error) {
        setEmotion(data.dominant_emotion);
        setProcessedImage(data.image);

        // 2) Log emotion distribution to timeline, if we have an interview
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

  // 3) Submit Answer
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
          console.log("Answer result:", data);
          if (data.message==="Answer submitted") {
            alert("Answer recorded successfully!");
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

  // Move to next question
  const handleNextQuestion = () => {
    if (currentQIndex < questions.length - 1) {
      setCurrentQIndex(currentQIndex + 1);
    } else {
      alert("All questions answered, finalize interview");
    }
  };

  // 4) Finalize
  const handleFinalizeInterview = async() => {
    try {
      const res = await fetch("http://localhost:5000/api/finalizeInterview", {
        method:"POST",
        headers:{
          "Content-Type":"application/json",
          "Clerk-User-Email": user.primaryEmailAddress.emailAddress
        },
        body: JSON.stringify({interviewId})
      });
      const data = await res.json();
      if (data.message==="Interview finalized") {
        // go to analysis page
        navigate("/analysis", { state:{ interviewId }});
      } else {
        alert(data.error || "Error finalizing interview");
      }
    } catch(err) {
      console.error("Finalize error:", err);
    }
  };

  return(
    <div style={{ textAlign:'center', marginTop:'20px'}}>
      <h1>Main Interview</h1>

      {/* Start Interview */}
      {!interviewId && (
        <button onClick={handleStartInterview}>Start Interview</button>
      )}

      {interviewId && (
        <>
          <p>Interview ID: {interviewId}</p>

          {/* Show question */}
          {questions.length > 0 && currentQIndex < questions.length && (
            <div>
              <h3>Question {currentQIndex + 1} of {questions.length}</h3>
              <p>{questions[currentQIndex]}</p>

              {!isRecording ? (
                <button onClick={handleStartRecording}>Record Answer</button>
              ) : (
                <button onClick={handleStopRecording}>Stop Recording</button>
              )}

              <button onClick={handleNextQuestion} style={{ marginLeft:'10px' }}>
                Next Question
              </button>
            </div>
          )}

          {currentQIndex >= questions.length && (
            <button onClick={handleFinalizeInterview}>
              Finalize Interview
            </button>
          )}
        </>
      )}

      <hr/>
      <h2>Emotion Tracking</h2>
      <div>
        {!stream ? (
          <button onClick={startVideo}>Start Camera</button>
        ) : (
          <button onClick={stopVideo}>Stop Camera</button>
        )}

        {!isCapturing ? (
          <button onClick={startCapturing} disabled={!stream} style={{ marginLeft:'10px' }}>
            Start Tracking
          </button>
        ) : (
          <button onClick={stopCapturing} style={{ marginLeft:'10px' }}>
            Stop Tracking
          </button>
        )}
      </div>

      <div style={{ marginTop:'20px' }}>
        <video ref={videoRef} style={{ width:'300px', border:'1px solid #ccc' }} />
        <p>Current Emotion: {emotion}</p>
        {processedImage && (
          <img 
            src={processedImage} 
            alt="Processed" 
            style={{ width:'300px', border:'1px solid #ccc', marginTop:'10px'}}
          />
        )}
      </div>
    </div>
  );
}

export default MainInterview;
