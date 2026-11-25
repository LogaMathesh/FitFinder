import React, { useState, useEffect } from 'react';
import './App.css';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import {
  UNAUTHORIZED_EVENT,
  clearSession,
  getDisplayName,
  hasValidSession,
  saveSession,
} from './lib/api';

import Header from './components/Header';
import Footer from './components/Footer';
import ErrorBoundary from './components/ErrorBoundary';

import Login from './pages/Login';
import Signup from './pages/Signup';
import History from './pages/History';
import Upload from './pages/Upload';
import Home from './pages/Home';
import About from './pages/About';
import IdeaSearch from './pages/IdeaSearch';
import Profile from './pages/Profile';
import Chatbot from './components/Chatbot';

function App() {
  // `user` is the display name of the signed-in user. It is only set while a
  // non-expired token is stored; the server identifies the user by the token.
  const [user, setUser] = useState(() => (hasValidSession() ? getDisplayName() : null));
  const navigate = useNavigate();

  useEffect(() => {
    if (!hasValidSession()) {
      clearSession();
    }

    const handleUnauthorized = () => {
      setUser(null);
      navigate('/login', { replace: true });
    };

    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [navigate]);

  const handleLogin = ({ user: username, token }) => {
    saveSession({ token, user: username });
    setUser(username);
  };

  const handleLogout = () => {
    clearSession();
    setUser(null);
  };

  return (
    <div className="app">
      <Header user={user} handleLogout={handleLogout} />

      <main>
        <ErrorBoundary>
          <Routes>
            {/* Public Routes */}
            <Route
              path="/"
              element={<Home user={user} />}
            />

            <Route
              path="/about"
              element={<About />}
            />

            <Route
              path="/login"
              element={
                !user ? (
                  <Login onLogin={handleLogin} />
                ) : (
                  <Navigate to="/" />
                )
              }
            />

            <Route
              path="/signup"
              element={
                !user ? (
                  <Signup onSignup={handleLogin} />
                ) : (
                  <Navigate to="/" />
                )
              }
            />

            {/* Protected Routes */}

            <Route
              path="/upload"
              element={
                user ? (
                  <Upload />
                ) : (
                  <Navigate to="/login" />
                )
              }
            />

            <Route
              path="/history"
              element={
                user ? (
                  <History username={user} />
                ) : (
                  <Navigate to="/login" />
                )
              }
            />

            <Route
              path="/profile"
              element={
                user ? (
                  <Profile username={user} />
                ) : (
                  <Navigate to="/login" />
                )
              }
            />

            <Route
              path="/chatbot"
              element={
                user ? (
                  <Chatbot currentUser={{ id: user }} />
                ) : (
                  <Navigate to="/login" />
                )
              }
            />

            <Route
              path="/idea-search"
              element={
                user ? (
                  <IdeaSearch user={user} />
                ) : (
                  <Navigate to="/login" />
                )
              }
            />
          </Routes>
        </ErrorBoundary>
      </main>

      <Footer />
    </div>
  );
}

export default App;