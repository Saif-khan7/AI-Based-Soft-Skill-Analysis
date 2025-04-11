// src/pages/ResumeUpload.js
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

  // ----------------------
  // Helper to parse JSON and produce bullet points
  // ----------------------
  const parseAnalysisToBullets = (analysisText) => {
    try {
      const obj = JSON.parse(analysisText);

      // We'll gather bullet points from known fields
      // Feel free to adjust which fields you want to show
      const bullets = [];

      if (obj.full_name) {
        bullets.push({ label: "Full Name", value: obj.full_name });
      }
      if (obj.contact_details) {
        bullets.push({ label: "Contact Details", value: obj.contact_details });
      }
      if (obj.professional_summary) {
        bullets.push({ label: "Professional Summary", value: obj.professional_summary });
      }
      if (obj.relevant_experience) {
        bullets.push({ label: "Relevant Experience", value: obj.relevant_experience });
      }
      if (obj.key_skills) {
        bullets.push({ label: "Key Skills", value: obj.key_skills });
      }
      if (obj.certifications) {
        bullets.push({ label: "Certifications", value: obj.certifications });
      }
      if (obj.industry_expertise) {
        bullets.push({ label: "Industry Expertise", value: obj.industry_expertise });
      }
      if (obj.match_score !== undefined) {
        bullets.push({ label: "Match Score", value: obj.match_score });
      }
      if (obj.match_explanation) {
        bullets.push({ label: "Match Explanation", value: obj.match_explanation });
      }

      // If we have bullet points, return them
      if (bullets.length > 0) {
        return bullets;
      } else {
        // No recognized fields found, fallback
        return null;
      }
    } catch (err) {
      // Not valid JSON
      return null;
    }
  };

  // We'll parse the analysis if possible
  const analysisBullets = parseAnalysisToBullets(analysis);

  // Some inline styles for a modern look
  const containerStyle = {
    fontFamily: 'Poppins, sans-serif',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '2rem'
  };

  const cardStyle = {
    maxWidth: '600px',
    width: '100%',
    backgroundColor: '#fff',
    boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
    borderRadius: '8px',
    padding: '1.5rem',
    marginTop: '2rem',
    textAlign: 'center'
  };

  const headingStyle = {
    marginBottom: '1rem',
    fontWeight: 600,
    color: '#333'
  };

  const fieldContainer = {
    margin: '1rem 0'
  };

  const labelStyle = {
    display: 'block',
    marginBottom: '0.5rem',
    color: '#555',
    fontWeight: 500
  };

  const inputStyle = {
    width: '100%',
    padding: '0.5rem',
    borderRadius: '4px',
    border: '1px solid #ccc',
    fontSize: '1rem'
  };

  const fileInputStyle = {
    marginRight: '10px'
  };

  const buttonStyle = {
    padding: '0.7rem 1.5rem',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '1rem',
    fontWeight: 500,
    backgroundColor: '#6454F0',
    color: '#fff',
    transition: 'background-color 0.3s'
  };

  const errorMsgStyle = {
    color: 'red',
    marginTop: '0.5rem'
  };

  const bulletContainerStyle = {
    textAlign: 'left',
    marginTop: '1rem',
    backgroundColor: '#f5f5f5',
    padding: '1rem',
    borderRadius: '4px'
  };

  const bulletTitleStyle = {
    marginBottom: '0.5rem',
    fontWeight: 600
  };

  const rawAnalysisStyle = {
    marginTop: '20px',
    whiteSpace: 'pre-wrap'
  };

  return (
    <div style={containerStyle}>
      <h1 style={{ fontWeight: 600, color: '#333' }}>Resume Analysis</h1>
      
      <div style={cardStyle}>
        <div style={fieldContainer}>
          <label style={labelStyle}>Select Your Resume (PDF or DOCX)</label>
          <input 
            type="file" 
            accept=".pdf,.docx" 
            onChange={handleFileChange}
            style={fileInputStyle}
          />
        </div>

        <div style={fieldContainer}>
          <label style={labelStyle}>Job Description (Optional)</label>
          <textarea
            value={jobDescription}
            onChange={handleJobDescriptionChange}
            placeholder="Paste or type job description here..."
            rows="4"
            style={inputStyle}
          />
        </div>

        {errorMsg && <p style={errorMsgStyle}>{errorMsg}</p>}

        <button 
          onClick={handleUpload} 
          style={{ ...buttonStyle, marginTop: '1rem' }}
          disabled={uploading}
        >
          {uploading ? "Analyzing..." : "Upload & Analyze"}
        </button>

        {analysis && (
          <div style={{ marginTop: '20px' }}>
            <h3 style={{ textAlign: 'left', marginBottom: '0.5rem' }}>
              Resume Analysis
            </h3>

            {/* If we have bullet points, show them. Otherwise, fallback to raw text */}
            {analysisBullets ? (
              <div style={bulletContainerStyle}>
                <ul style={{ paddingLeft: '1.5rem' }}>
                  {analysisBullets.map((item, i) => (
                    <li key={i} style={{ marginBottom: '0.5rem' }}>
                      <strong>{item.label}:</strong> {item.value}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <pre style={{ ...rawAnalysisStyle, backgroundColor: '#f5f5f5', padding: '10px', borderRadius: '4px' }}>
                {analysis}
              </pre>
            )}

            <button
              style={{
                ...buttonStyle,
                marginTop: '1rem',
                backgroundColor: '#ffca28',
                color: '#333'
              }}
              onClick={handleProceed}
            >
              Proceed to Interview
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default ResumeUpload;
