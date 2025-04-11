// src/App.js
import React from 'react';
import { BrowserRouter as Router, Routes, Route} from 'react-router-dom';
import { 
  SignedIn, 
  SignedOut, 
  RedirectToSignIn, 
  SignIn, 
  SignUp, 
  SignInButton, 
  UserButton 
} from '@clerk/clerk-react';

import Dashboard from './pages/Dashboard';
import ResumeUpload from './pages/ResumeUpload';
import Interview from './pages/Interview';
import MainInterview from './pages/MainInterview';
import Analysis from './pages/Analysis';
import AnswerAssessment from './pages/AnswerAssessment';

function App() {
  const headerStyle = {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '1rem 2rem',
    boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    backgroundColor: '#fdfdfd',
    fontFamily: 'Poppins, sans-serif'
  };

  const titleStyle = {
    margin: 0,
    fontWeight: 600,
    fontSize: '1.4rem'
  };

  return (
    <Router>
      <header style={headerStyle}>
        <h1 style={titleStyle}>Soft Skill Interview Platform</h1>
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
        {/* Public route for Dashboard */}
        <Route path="/" element={<Dashboard />} />

        {/* Clerk sign-in & sign-up pages */}
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
        <Route path="/sign-up/*" element={<SignUp routing="path" path="/sign-up" />} />

        {/* Protected routes: require SignedIn */}
        <Route 
          path="/resume" 
          element={
            <SignedIn>
              <ResumeUpload />
            </SignedIn>
          }
        />
        <Route 
          path="/Interview" 
          element={
            <SignedIn>
              <Interview />
            </SignedIn>
          }
        />
        <Route 
          path="/mainInterview" 
          element={
            <SignedIn>
              <MainInterview />
            </SignedIn>
          }
        />
        <Route 
          path="/answerAssessment" 
          element={
            <SignedIn>
              <AnswerAssessment />
            </SignedIn>
          }
        />
        <Route 
          path="/analysis" 
          element={
            <SignedIn>
              <Analysis />
            </SignedIn>
          }
        />

        {/* Catch-all -> if not signed in, redirect */}
        <Route
          path="*"
          element={
            <SignedOut>
              <RedirectToSignIn />
            </SignedOut>
          }
        />
      </Routes>
    </Router>
  );
}

export default App;
