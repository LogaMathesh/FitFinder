import React, { useState } from 'react';
import './IdeaSearch.css';
import { apiFetch } from '../lib/api';
import { describeFailure, readJson, shortWait, usageLevel, useUsage } from '../lib/usage';
import { Helmet } from "react-helmet-async";

export default function IdeaSearch({ user }) {
  const [idea, setIdea] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState([]);
  const [queryUsed, setQueryUsed] = useState('');
  // { kind: 'error' | 'limit' | 'empty', text }
  const [notice, setNotice] = useState(null);
  const { usage, secondsToReset, outOfCredits, checking, applyUsage } = useUsage('idea_search');

  const [interactions, setInteractions] = useState({});

  const handleSearch = async (e) => {
    e.preventDefault();
    if (!idea.trim() || loading || outOfCredits) return;

    setLoading(true);
    setResults([]);
    setNotice(null);
    setQueryUsed('');
    setInteractions({});

    try {
      const response = await apiFetch('/search-ideas', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea })
      });

      const data = await readJson(response);
      applyUsage(data.usage);

      if (response.ok) {
        const found = data.results || [];
        setResults(found);
        setQueryUsed(data.query_used || '');
        if (found.length === 0) {
          setNotice({ kind: 'empty', text: 'No matches found, try describing it differently.' });
        }
      } else {
        setNotice({
          kind: response.status === 429 ? 'limit' : 'error',
          text: describeFailure(response, data),
        });
      }
    } catch {
      setNotice({ kind: 'error', text: describeFailure(null) });
    } finally {
      setLoading(false);
    }
  };

  const handleInteraction = async (e, item, type, index) => {
    e.preventDefault(); // Prevent navigating to the link
    if (!user) {
        alert("Please log in to save preferences!");
        return;
    }
    
    // Optimistic UI update
    setInteractions(prev => ({
        ...prev,
        [index]: type
    }));

    try {
        await apiFetch('/interact', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                item: item,
                type: type
            })
        });
    } catch (err) {
        console.error("Failed to save interaction", err);
    }
  };

  return (
    <div className="idea-search-container">
      <Helmet>
  <title>AI Outfit Ideas & Fashion Recommendations | FitFinder</title>
  <meta
    name="description"
    content="Get AI-generated outfit ideas for parties, weddings, office wear, travel, beach vacations, casual outings, and special occasions."
  />
  <meta
    name="keywords"
    content="outfit ideas, fashion recommendations, wedding outfit ideas, party outfits, beach outfits, travel fashion"
  />
</Helmet>
      <h2>✨ Magic Dress Idea Search</h2>
      <p className="idea-subtitle">Describe your dream dress in plain text, and our AI will track it down online!</p>
      
      <form onSubmit={handleSearch} className="idea-form">
        <textarea
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="e.g., A flowy emerald green dress perfect for a winter formal gala"
          rows={3}
        />
        <button type="submit" disabled={loading || outOfCredits || !idea.trim()} className="btn btn-gradient search-btn">
          {loading
            ? 'Searching the web...'
            : outOfCredits
              ? `Try again in ${shortWait(secondsToReset)}`
              : 'Find Matches'}
        </button>
      </form>

      {usage && (
        <p className={`usage-line ${usageLevel(usage)}`}>
          {usage.remaining} of {usage.limit} searches left
          {secondsToReset !== null && usage.remaining < usage.limit && (
            <> · next in {shortWait(secondsToReset)}</>
          )}
        </p>
      )}
      {checking && <p className="usage-line checking">Checking credits…</p>}

      {notice &&<div className={`notice-box ${notice.kind}`}>{notice.text}</div>}

      {queryUsed && (
        <div className="query-box">
          <strong>AI actively searched for: </strong> "{queryUsed}"
        </div>
      )}

      {loading && <div className="spinner idea-spinner" />}

      {results.length > 0 && (
        <div className="idea-results">
          {results.map((item, idx) => (
            <a href={item.link} target="_blank" rel="noopener noreferrer" className="idea-card" key={idx}>
              <div className="card-img-container">
                <img src={item.thumbnail} alt={item.title} />
              </div>
              <div className="card-info">
                <h4 className="card-title">{item.title}</h4>
                <p className="card-price">{item.price}</p>
                <p className="card-source">{item.source}</p>
              </div>
              <div className="card-interactions">
                <button 
                  className={`interaction-btn ${interactions[idx] === 'like' ? 'active-like' : ''}`}
                  onClick={(e) => handleInteraction(e, item, 'like', idx)}
                  title="I like this style"
                >
                  👍
                </button>
                <button 
                  className={`interaction-btn ${interactions[idx] === 'dislike' ? 'active-dislike' : ''}`}
                  onClick={(e) => handleInteraction(e, item, 'dislike', idx)}
                  title="Show me less like this"
                >
                  👎
                </button>
                <button 
                  className={`interaction-btn ${interactions[idx] === 'save' ? 'active-save' : ''}`}
                  onClick={(e) => handleInteraction(e, item, 'save', idx)}
                  title="Save for later"
                >
                  💾
                </button>
              </div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
