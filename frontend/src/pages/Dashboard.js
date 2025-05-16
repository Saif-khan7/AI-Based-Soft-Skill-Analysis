// src/pages/Dashboard.js
import React from 'react';
import { useNavigate } from 'react-router-dom';

function Dashboard() {
  const navigate = useNavigate();

  const handleStartInterview = () => {
    navigate('/resume');
  };

  const heroStyle = {
    width: '100%',
    minHeight: '70vh',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    background: 'linear-gradient(135deg, #6EE2F5 0%, #6454F0 100%)',
    color: '#fff',
    textAlign: 'center',
    padding: '2rem',
    fontFamily: 'Poppins, sans-serif'
  };

  const titleStyle = {
    fontSize: '2.5rem',
    fontWeight: 600,
    marginBottom: '1rem',
    maxWidth: '800px',
    lineHeight: 1.2
  };

  const subtitleStyle = {
    fontSize: '1.1rem',
    maxWidth: '600px',
    margin: '0 auto 2rem auto',
    opacity: 0.9
  };

  const buttonContainerStyle = {
    display: 'flex',
    gap: '1rem',
    marginTop: '1.5rem'
  };

  const buttonStyle = {
    padding: '0.8rem 1.5rem',
    fontSize: '1rem',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontFamily: 'Poppins, sans-serif',
    boxShadow: '0 2px 6px rgba(0,0,0,0.2)',
    transition: 'background-color 0.3s'
  };

  const startButtonStyle = {
    ...buttonStyle,
    backgroundColor: '#ffca28',
    color: '#2f2f2f',
    fontWeight: 600
  };

  const docButtonStyle = {
    ...buttonStyle,
    backgroundColor: '#fff',
    color: '#6454F0',
    fontWeight: 500
  };

  const handleViewBridge = () => {
    window.open('https://bridgeetal.com', '_blank');
  };

  const handleViewChange = () => {
    window.open('https://changetal.com/', '_blank');
  };

  return (
    <div style={{ fontFamily: 'Poppins, sans-serif' }}>
      <section style={heroStyle}>
        <h1 style={titleStyle}>Empower Your Soft Skills with AI</h1>
        <p style={subtitleStyle}>
          Leverage cutting-edge speech analysis, real-time emotion tracking, 
          and dynamic skill matching to elevate your career. 
          Upload your resume and let our platform do the rest.
        </p>

        <div style={buttonContainerStyle}>
          <button style={startButtonStyle} onClick={handleStartInterview}>
            Start Interview
          </button>
          <button style={docButtonStyle} onClick={handleViewBridge}>
            View Bridge et al
          </button>
          <button style={docButtonStyle} onClick={handleViewChange}>
            View Change et al
          </button>
        </div>
      </section>

      {/* Additional info or features could go below */}
      <div style={{ textAlign: 'center', padding: '2rem', fontSize: '1rem', color: '#333' }}>
        <h2 style={{ marginBottom: '1rem', fontWeight: 600 }}>Why Choose Our Platform?</h2>
        <div style={{ maxWidth: '700px', margin: '0 auto', lineHeight: '1.6' }}>
          <p>
            Our platform combines AI-driven speech transcription, emotion analysis, 
            and skill-based interviewing to give you comprehensive feedback on 
            your communication style. The result? A faster, more efficient way 
            to refine your soft skills and ace your next interview.
          </p>
          <p>
            Whether you’re a seasoned professional or just starting out, our 
            real-time metrics and LLM-based assessments provide actionable insights 
            to help you grow.
          </p>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
