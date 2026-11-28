import React, { useEffect, useState } from 'react';
import './Login.css'; 
import { apiUrl } from '../lib/api';
import { Helmet } from "react-helmet-async";

const OAUTH_ERRORS = {
  account_conflict: 'This Google account conflicts with an existing FitFinder account. Sign in with your username and password.',
  google_auth_failed: 'Google sign-in could not be completed. Please try again.',
  not_configured: 'Google sign-in is not configured yet.',
  server_error: 'Google sign-in failed. Please try again.',
};

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    const fragment = window.location.hash;
    if (!fragment) return;

    const params = new URLSearchParams(fragment.slice(1));
    const code = params.get('oauth_code');
    const oauthError = params.get('oauth_error');
    if (!code && !oauthError) return;

    window.history.replaceState(
      window.history.state,
      '',
      `${window.location.pathname}${window.location.search}`,
    );

    if (oauthError) {
      setMessage(OAUTH_ERRORS[oauthError] || OAUTH_ERRORS.google_auth_failed);
      return;
    }

    setIsLoading(true);
    setMessage('');
    fetch(apiUrl('/auth/google/exchange'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    })
      .then(async (res) => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Google login failed');
        onLogin({ user: data.user, token: data.token });
      })
      .catch(() => setMessage('Google sign-in failed. Please try again.'))
      .finally(() => setIsLoading(false));
  }, [onLogin]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setMessage('');
    
    try {
      const res = await fetch(apiUrl('/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage('Login successful!');
        setTimeout(() => onLogin({ user: data.user, token: data.token }), 1000);
      } else {
        setMessage(data.error || 'Login failed');
      }
    } catch {
      setMessage('Network error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    setIsLoading(true);
    setMessage('');
    window.location.assign(apiUrl('/auth/google'));
  };

  return (
    <form onSubmit={handleLogin} className="login-container">
      <Helmet>
  <title>Login | FitFinder</title>
  <meta
    name="description"
    content="Login to FitFinder to access your AI-powered wardrobe, outfit history, and personalized fashion recommendations."
  />
</Helmet>
      <h2>Welcome Back</h2>
      
      <div className="form-group">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          type="text"
          placeholder="Enter your username"
          value={username}
          onChange={e => setUsername(e.target.value)}
          required
          disabled={isLoading}
        />
      </div>
      
      <div className="form-group">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          placeholder="Enter your password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          disabled={isLoading}
        />
      </div>
      
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Signing In...' : 'Sign In'}
      </button>

      <div className="login-divider" aria-hidden="true"><span>or</span></div>

      <button
        type="button"
        className="google-login-button"
        onClick={handleGoogleLogin}
        disabled={isLoading}
      >
        Continue with Google
      </button>
      
      {message && (
        <p className={message.includes('successful') ? 'success' : 'error'}>
          {message}
        </p>
      )}
    </form>
  );
}
