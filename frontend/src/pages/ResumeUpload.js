import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUser } from '@clerk/clerk-react';

function ResumeUpload() {
  const navigate = useNavigate();
  const { user } = useUser();
  const [resumeFile, setResumeFile] = useState(null);
  const [jobDescription, setJobDescription] = useState("");
  const [analysis, setAnalysis] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [uploading, setUploading] = useState(false);

  const handleFileChange = (e) => {
    setResumeFile(e.target.files[0]);
  };

  const handleJobDescriptionChange = (e) => {
    setJobDescription(e.target.value);
  };

  const handleUpload = async () => {
    if (!resumeFile) {
      setErrorMsg("Please select a resume file.");
      return;
    }
    setErrorMsg("");
    setUploading(true);
    setAnalysis("");

    try {
      const formData = new FormData();
      formData.append("resumeFile", resumeFile);
      if (jobDescription.trim()) {
        formData.append("jobDescription", jobDescription);
      }

      // Include the user's email from Clerk in the headers
      const res = await fetch("http://localhost:5000/api/resume", {
        method: "POST",
        headers: {
          "Clerk-User-Email": user.primaryEmailAddress.emailAddress
        },
        body: formData
      });
      const data = await res.json();
      console.log("Resume analysis response:", data);
      if (res.ok) {
        setAnalysis(data.analysis || "No analysis returned.");
      } else {
        setErrorMsg(data.error || "Error analyzing resume.");
      }
    } catch (err) {
      console.error("Resume upload error:", err);
      setErrorMsg("Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleProceed = () => {
    navigate('/interview');
  };

  return (
    <div style={{ textAlign: 'center', marginTop: '40px' }}>
      <h1>Resume Analysis</h1>
      <div style={{ margin: '20px' }}>
        <input 
          type="file" 
          accept=".pdf,.docx" 
          onChange={handleFileChange} 
          style={{ marginRight: '10px' }} 
        />
        <button onClick={handleUpload} disabled={uploading}>
          {uploading ? "Analyzing..." : "Upload Resume"}
        </button>
      </div>
      <div style={{ margin: '20px' }}>
        <textarea
          value={jobDescription}
          onChange={handleJobDescriptionChange}
          placeholder="Enter Job Description (Optional)"
          rows="4"
          style={{ width: '60%' }}
        />
      </div>
      {errorMsg && <p style={{ color: 'red' }}>{errorMsg}</p>}
      {analysis && (
        <div style={{ marginTop: '20px', maxWidth: '600px', margin: '0 auto', textAlign: 'left' }}>
          <h3>Resume Analysis</h3>
          <pre style={{ whiteSpace: 'pre-wrap', backgroundColor: '#f5f5f5', padding: '10px', borderRadius: '4px' }}>
            {analysis}
          </pre>
          <button
            style={{ marginTop: '20px', padding: '10px 20px', cursor: 'pointer' }}
            onClick={handleProceed}
          >
            Proceed to Interview
          </button>
        </div>
      )}
    </div>
  );
}

export default ResumeUpload;
