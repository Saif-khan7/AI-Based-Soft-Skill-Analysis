import React, { useRef, useState, useEffect } from 'react';

function Interview() {
  const videoRef = useRef(null);
  const [stream, setStream] = useState(null);
  const [processedImage, setProcessedImage] = useState(null);
  const [emotion, setEmotion] = useState('');
  const [isCapturing, setIsCapturing] = useState(false);
  const captureIntervalRef = useRef(null);

  const [audioRecorder, setAudioRecorder] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [audioResult, setAudioResult] = useState(null);
  const audioChunksRef = useRef([]);

  useEffect(() => {
    return () => {
      stopCapturing();
      stopVideo();
      if (audioRecorder) {
        audioRecorder.stop();
      }
    };
    // eslint-disable-next-line
  }, []);

  const startVideo = async () => {
    try {
      const userStream = await navigator.mediaDevices.getUserMedia({ video: true });
      setStream(userStream);
      if (videoRef.current) {
        videoRef.current.srcObject = userStream;
        videoRef.current.play();
      }
    } catch (err) {
      console.error('Error accessing webcam:', err);
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
    captureIntervalRef.current = setInterval(() => {
      captureFrame();
    }, 2000);
  };

  const stopCapturing = () => {
    setIsCapturing(false);
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
    }
  };

  const captureFrame = async () => {
    if (!videoRef.current) return;
    const canvas = document.createElement('canvas');
    canvas.width = videoRef.current.videoWidth;
    canvas.height = videoRef.current.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);

    const base64Image = canvas.toDataURL('image/jpeg');
    console.log('Captured base64 length:', base64Image.length);

    try {
      const response = await fetch('http://localhost:5000/analyzeFrame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: base64Image }),
      });
      const data = await response.json();
      if (!data.error) {
        setEmotion(data.emotion);
        setProcessedImage(data.image);
      } else {
        console.error('DeepFace error:', data.error);
      }
    } catch (error) {
      console.error('Error sending frame to server:', error);
    }
  };

  const startRecording = async () => {
    try {
      const audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(audioStream);
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        console.log("DEBUG: Recorded audio blob size =", audioBlob.size);

        const formData = new FormData();
        formData.append("audio", audioBlob, "recording.wav");

        try {
          const res = await fetch("http://localhost:5000/processAudio", {
            method: "POST",
            body: formData
          });
          const resultData = await res.json();
          if (!resultData.error) {
            setAudioResult(resultData);
          } else {
            console.error("Audio analysis error:", resultData.error);
          }
        } catch (err) {
          console.error("Error uploading audio:", err);
        }
      };

      recorder.start();
      setAudioRecorder(recorder);
      setIsRecording(true);
      setAudioResult(null);
    } catch (err) {
      console.error("Error starting audio recording:", err);
    }
  };

  const stopRecording = () => {
    if (audioRecorder) {
      audioRecorder.stop();
      audioRecorder.stream.getTracks().forEach(track => track.stop());
    }
    setIsRecording(false);
    setAudioRecorder(null);
  };

  return (
    <div style={{ textAlign: 'center', marginTop: '20px' }}>
      <h1>Interview Session</h1>
      
      <section style={{ marginBottom: '30px' }}>
        <h2>Continuous Emotion Tracking (DeepFace)</h2>
        <video ref={videoRef} style={{ width: '60%', border: '2px solid #ccc' }} />
        <div style={{ marginTop: '10px' }}>
          {!stream ? (
            <button onClick={startVideo}>Start Camera</button>
          ) : (
            <button onClick={stopVideo}>Stop Camera</button>
          )}
          {!isCapturing ? (
            <button onClick={startCapturing} style={{ marginLeft: '10px' }} disabled={!stream}>
              Start Tracking
            </button>
          ) : (
            <button onClick={stopCapturing} style={{ marginLeft: '10px' }}>
              Stop Tracking
            </button>
          )}
        </div>
        {processedImage && (
          <div style={{ marginTop: '20px' }}>
            <h3>Server Processed Frame</h3>
            <img src={processedImage} alt="Processed Frame" style={{ width: '60%', border: '2px solid #ccc' }} />
          </div>
        )}
        {emotion && (
          <div style={{ marginTop: '10px' }}>
            <h2>Detected Emotion: {emotion}</h2>
          </div>
        )}
      </section>

      <section>
        <h2>Speech Analysis (Whisper)</h2>
        {!isRecording ? (
          <button onClick={startRecording}>Start Recording</button>
        ) : (
          <button onClick={stopRecording}>Stop Recording</button>
        )}
        {audioResult && (
          <div style={{ marginTop: '20px', textAlign: 'left', marginInline: '20%' }}>
            <p><strong>Detected Language:</strong> {audioResult.language}</p>
            <p><strong>Transcript:</strong> {audioResult.transcript}</p>
            <p><strong>Speech Rate (WPM):</strong> {audioResult.speechRateWPM}</p>
            <p><strong>Filler Rate:</strong> {audioResult.fillerRate}</p>
            <p><strong>Filler Count:</strong> {audioResult.fillerCount}</p>
            <p><strong>Filler Words Used:</strong> {JSON.stringify(audioResult.fillerWordsUsed)}</p>
          </div>
        )}
      </section>
    </div>
  );
}

export default Interview;
