import React, { useState, useRef, useEffect, useMemo } from "react";
import "./Chatbot.css";
import { apiFetch } from "../lib/api";
import { describeFailure, readJson, shortWait, usageLevel, useUsage } from "../lib/usage";
import { Bot, Image, Send, Sparkles, Trash2, User } from "lucide-react";
import { Helmet } from "react-helmet-async";

const Chatbot = ({ currentUser }) => {
  const historyKey = useMemo(
    () => `fitfinder_chat_history_${currentUser?.id || "guest"}`,
    [currentUser?.id]
  );
  const [messages, setMessages] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(historyKey)) || [];
    } catch {
      return [];
    }
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedImage, setSelectedImage] = useState(null);
  const chatEndRef = useRef(null);
  const { usage, secondsToReset, outOfCredits, checking, applyUsage } = useUsage("chatbot");

  useEffect(() => {
    try {
      setMessages(JSON.parse(localStorage.getItem(historyKey)) || []);
    } catch {
      setMessages([]);
    }
  }, [historyKey]);

  useEffect(() => {
    if (messages.length === 0) {
      localStorage.removeItem(historyKey);
      return;
    }

    localStorage.setItem(historyKey, JSON.stringify(messages));
  }, [historyKey, messages]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading || outOfCredits) return;

    const query = input.trim();
    setMessages((prev) => [...prev, { type: "user", text: query }]);
    setLoading(true);

    try {
      const res = await apiFetch("/chatbot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      const data = await readJson(res);
      applyUsage(data.usage);

      if (!res.ok) {
        const kind = res.status === 429 ? "limit" : "error";
        setMessages((prev) => [...prev, { type: "bot", kind, text: describeFailure(res, data) }]);
        return;
      }

      let botReply;
      let images = [];

      if (data.results && data.results.length > 0) {
        const topResults = data.results.slice(0, 3);
        botReply = `Here are the top ${topResults.length} items I found:`;
        images = topResults.map((r, index) => ({
          url: r.url,
          style: r.style,
          index: index + 1
        }));
      } else {
        botReply =
          "I couldn't find any items matching your query. Try uploading images first or use different terms like 'formal wear' or 'summer outfit'.";
      }

      setMessages((prev) => [...prev, { type: "bot", text: botReply, images }]);
    } catch {
      setMessages((prev) => [...prev, { type: "bot", kind: "error", text: describeFailure(null) }]);
    } finally {
      setInput("");
      setLoading(false);
    }
  };

  const clearHistory = () => {
    setMessages([]);
    localStorage.removeItem(historyKey);
  };

  return (
    <div className="chatbot-container">
      <Helmet>
  <title>AI Fashion Chatbot | FitFinder</title>
  <meta
    name="description"
    content="Ask our AI fashion chatbot for outfit suggestions, dress combinations, styling advice, and wardrobe recommendations."
  />
  <meta
    name="keywords"
    content="fashion chatbot, AI stylist, outfit advisor, wardrobe assistant"
  />
</Helmet>
      <div className="chatbot-header">
        <div className="assistant-mark">
          <Bot size={22} />
        </div>
        <div>
          <h2>Fashion Assistant</h2>
          <p>Ask about outfits, occasions, colors, or saved wardrobe items.</p>
        </div>
        {usage && (
          <span
            className={`usage-badge ${usageLevel(usage)}`}
            title="Chats you can send in a rolling 30-minute window"
          >
            {usage.remaining} / {usage.limit} chats left
            {secondsToReset !== null && usage.remaining < usage.limit && (
              <> · next in {shortWait(secondsToReset)}</>
            )}
          </span>
        )}
        {checking && <span className="usage-badge checking">Checking credits…</span>}
        {messages.length > 0 && (
          <button className="clear-chat-button" onClick={clearHistory} title="Clear chat history" aria-label="Clear chat history">
            <Trash2 size={17} />
          </button>
        )}
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-placeholder">
            <Sparkles size={28} />
            <h3>How can I style your wardrobe today?</h3>
            <p>Try asking: "What should I wear for a job interview?"</p>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`chat-message ${m.type} ${m.kind || ""}`}>
              <span className="message-avatar">
                {m.type === "user" ? <User size={15} /> : <Bot size={15} />}
              </span>
              <div className="chat-text">{m.text}</div>
              {m.images && m.images.length > 0 && (
                <div className="image-grid">
                  {m.images.map((img, idx) => (
                    <div key={idx} className="image-card">
                      <img
                        src={img.url}
                        alt={`Recommendation ${img.index}`}
                        onClick={() => setSelectedImage(img)}
                      />
                      <span><Image size={13} /> {img.style || "Saved look"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="chat-message bot loading-message">
            <span className="message-avatar"><Bot size={15} /></span>
            <div className="typing-dots"><span></span><span></span><span></span></div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          placeholder={
            outOfCredits
              ? `Chat limit reached, try again in ${shortWait(secondsToReset)}`
              : "Ask for dress suggestions..."
          }
          disabled={outOfCredits}
        />
        <button onClick={sendMessage} disabled={loading || outOfCredits || !input.trim()}>
          <Send size={17} />
          <span>{loading ? "Sending" : "Send"}</span>
        </button>
      </div>

      {selectedImage && (
        <div className="image-modal-overlay" onClick={() => setSelectedImage(null)}>
          <div className="image-modal" onClick={(e) => e.stopPropagation()}>
            <button className="image-modal-close" onClick={() => setSelectedImage(null)}>
              x
            </button>
            <img src={selectedImage.url} alt={`Recommendation ${selectedImage.index}`} />
            <div className="image-modal-info">
              <h3>Style: {selectedImage.style}</h3>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Chatbot;
