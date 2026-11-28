import React, { useEffect, useState } from 'react';
import './Signup.css';
import { apiUrl } from '../lib/api';
import { Helmet } from "react-helmet-async";

export default function Signup({ onSignup }) {
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
      const oauthErrors = {
        account_conflict: 'This Google account conflicts with an existing FitFinder account. Sign in with your username and password.',
        google_auth_failed: 'Google sign-in could not be completed. Please try again.',
        not_configured: 'Google sign-in is not configured yet.',
        server_error: 'Google sign-in failed. Please try again.',
      };
      setMessage(oauthErrors[oauthError] || oauthErrors.google_auth_failed);
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
        if (!res.ok) throw new Error(data.error || 'Google signup failed');
        onSignup({
          user: data.user,
          token: data.token,
          onboardingRequired: data.onboarding_required === true,
        });
      })
      .catch(() => setMessage('Google signup failed. Please try again.'))
      .finally(() => setIsLoading(false));
  }, [onSignup]);

  const handleSignup = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setMessage('');
    
    try {
      const res = await fetch(apiUrl('/signup'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      });
      const data = await res.json();
      if (res.ok) {
        setMessage('Signup successful! Welcome aboard!');
        setTimeout(() => onSignup({
          user: data.user,
          token: data.token,
          onboardingRequired: data.onboarding_required === true,
        }), 1500);
      } else {
        setMessage(data.error || 'Signup failed');
      }
    } catch {
      setMessage('Network error. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleSignup = () => {
    setIsLoading(true);
    setMessage('');
    window.location.assign(apiUrl('/auth/google?next=signup'));
  };

  return (
    <form onSubmit={handleSignup}>
      <Helmet>
  <title>Create Your FitFinder Account</title>
  <meta
    name="description"
    content="Sign up for FitFinder and start receiving personalized AI outfit recommendations and wardrobe insights."
  />
</Helmet>
      <h2>Join FitFinder</h2>
      
      <div className="form-group">
        <label htmlFor="username">Username</label>
        <input
          id="username"
          type="text"
          placeholder="Choose a username"
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
          placeholder="Create a strong password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          disabled={isLoading}
        />
      </div>
      
      <button type="submit" disabled={isLoading}>
        {isLoading ? 'Creating Account...' : 'Create Account'}
      </button>

      <div className="signup-divider" aria-hidden="true"><span>or</span></div>

      <button
        type="button"
        className="google-signup-button"
        onClick={handleGoogleSignup}
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
