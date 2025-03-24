import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { SignedIn, SignedOut, RedirectToSignIn, SignInButton, UserButton } from '@clerk/clerk-react';
import Dashboard from './pages/Dashboard';
import ResumeUpload from './pages/ResumeUpload';
import Interview from './pages/Interview';

function App() {
  return (
    <Router>
      <header style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        padding: '1rem', 
        borderBottom: '1px solid #ccc' 
      }}>
        <h1>Soft Skill Interview Platform</h1>
        <div>
          <SignedIn>
            <UserButton />
          </SignedIn>
          <SignedOut>
            <SignInButton />
          </SignedOut>
        </div>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/resume" element={<ResumeUpload />} />
        <Route path="/interview" element={<Interview />} />
        <Route path="*" element={<SignedOut><RedirectToSignIn /></SignedOut>} />
      </Routes>
    </Router>
  );
}

export default App;
