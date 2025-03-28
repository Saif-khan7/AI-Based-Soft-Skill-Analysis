import React from 'react';
import { useNavigate } from 'react-router-dom';

function Dashboard() {
  const navigate = useNavigate();

  const handleStartInterview = () => {
    navigate('/resume');
  };

  return (
    <div style={{ textAlign: 'center', marginTop: '50px' }}>
      <h1>Welcome to the Soft Skill Interview Platform</h1>
      <p style={{ maxWidth: '600px', margin: '20px auto' }}>
        Upload your resume to extract your skills and details, then proceed to a live interview session
        with real-time emotion tracking and speech analysis.
      </p>
      <button
        style={{ padding: '10px 20px', fontSize: '16px', cursor: 'pointer' }}
        onClick={handleStartInterview}
      >
        Start Interview
      </button>
    </div>
  );
}

export default Dashboard;
