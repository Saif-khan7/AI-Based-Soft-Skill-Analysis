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
import Interview from './pages/Interview';        // Old test interview
import MainInterview from './pages/MainInterview';// New main interview
import Analysis from './pages/Analysis';

function App() {
  return (
    <Router>
      {/* Header with brand name & sign-in logic */}
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
        {/* 1) Public route for Dashboard */}
        <Route path="/" element={<Dashboard />} />

        {/* 2) Clerk’s built-in sign-in & sign-up pages */}
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
        <Route path="/sign-up/*" element={<SignUp routing="path" path="/sign-up" />} />

        {/* 3) Protected routes: require SignedIn */}
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
          path="/analysis" 
          element={
            <SignedIn>
              <Analysis />
            </SignedIn>
          }
        />

        {/* 4) Catch-all -> if not signed in, redirect to /sign-in */}
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
