import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
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

function App() {
  return (
    <Router>
      {/* Optional simple header */}
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
        {/* 1) Public route: Dashboard is always visible */}
        <Route path="/" element={<Dashboard />} />

        {/* 2) Clerk’s built-in sign-in and sign-up pages */}
        <Route path="/sign-in/*" element={<SignIn routing="path" path="/sign-in" />} />
        <Route path="/sign-up/*" element={<SignUp routing="path" path="/sign-up" />} />

        {/* 3) Protected routes: resume & interview require sign-in */}
        <Route 
          path="/resume" 
          element={
            <SignedIn>
              <ResumeUpload />
            </SignedIn>
          }
        />
        <Route 
          path="/interview" 
          element={
            <SignedIn>
              <Interview />
            </SignedIn>
          }
        />

        {/* 4) Catch-all: if not signed in, Clerk will redirect to /sign-in */}
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
