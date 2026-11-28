import React, { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { ArrowLeft, ArrowRight, CalendarDays, Check, Heart, Palette, Shirt, Sparkles } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { EMPTY_PREFERENCES, PREFERENCE_QUESTIONS } from '../lib/preferences';
import './PreferenceOnboarding.css';

const QUESTION_ICONS = [Shirt, CalendarDays, Palette, Heart, Sparkles];
const MAX_SELECTIONS = 5;
const MotionDiv = motion.div;

export default function PreferenceOnboarding({ onComplete, onSkip }) {
  const [step, setStep] = useState(0);
  const [preferences, setPreferences] = useState(EMPTY_PREFERENCES);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const headingRef = useRef(null);
  const shouldReduceMotion = useReducedMotion();
  const question = PREFERENCE_QUESTIONS[step];
  const Icon = QUESTION_ICONS[step];
  const selected = preferences[question.field];

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  const toggleOption = (option) => {
    setPreferences((current) => {
      const currentSelections = current[question.field];
      if (currentSelections.includes(option)) {
        return {
          ...current,
          [question.field]: currentSelections.filter((item) => item !== option),
        };
      }
      if (currentSelections.length >= MAX_SELECTIONS) return current;
      return {
        ...current,
        [question.field]: [...currentSelections, option],
      };
    });
    setMessage('');
  };

  const handleContinue = async () => {
    if (step < PREFERENCE_QUESTIONS.length - 1) {
      setStep((current) => current + 1);
      return;
    }

    setLoading(true);
    setMessage('');
    try {
      const response = await apiFetch('/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ preferences }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'Could not save your preferences. Please try again.');
      }
      onComplete();
    } catch (error) {
      setMessage(error.message || 'Connection error. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const transitionDuration = shouldReduceMotion ? 0 : 0.24;

  return (
    <section className="preference-onboarding" aria-label="Style preference setup">
      <header className="onboarding-topbar">
        <button
          type="button"
          className="onboarding-back"
          onClick={() => setStep((current) => current - 1)}
          aria-label="Go to previous question"
          disabled={loading || step === 0}
        >
          <ArrowLeft size={20} />
        </button>
        <span>Style Preference</span>
        <span className="onboarding-topbar-mark" aria-hidden="true"><Sparkles size={17} /></span>
      </header>

      <div className="onboarding-content">
        <div className="onboarding-intro">
          <span className="onboarding-kicker">A little more you</span>
          <h1>Let’s find your style</h1>
          <p>Quick picks help us make outfit ideas feel more personal. You can skip or change these anytime.</p>
        </div>

        <div className="onboarding-question-progress" aria-live="polite">
          <span>QUESTION {step + 1} OF {PREFERENCE_QUESTIONS.length}</span>
          <span>{Math.round(((step + 1) / PREFERENCE_QUESTIONS.length) * 100)}% Complete</span>
        </div>
        <div
          className="onboarding-progress-track"
          role="progressbar"
          aria-label="Preference setup progress"
          aria-valuemin={0}
          aria-valuemax={PREFERENCE_QUESTIONS.length}
          aria-valuenow={step + 1}
        >
          <span style={{ width: `${((step + 1) / PREFERENCE_QUESTIONS.length) * 100}%` }} />
        </div>

        <div className="onboarding-question-window">
          <AnimatePresence mode="wait" initial={false}>
            <MotionDiv
              key={question.field}
              className="onboarding-question"
              initial={{ opacity: 0, x: shouldReduceMotion ? 0 : 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: shouldReduceMotion ? 0 : -20 }}
              transition={{ duration: transitionDuration, ease: 'easeOut' }}
              onAnimationComplete={() => headingRef.current?.focus()}
            >
              <div className="onboarding-question-heading">
                <span className="onboarding-question-icon"><Icon size={22} /></span>
                <h2 ref={headingRef} tabIndex="-1">{question.title}</h2>
                <p>{question.description}</p>
              </div>

              <div className="onboarding-options" role="group" aria-label={question.title}>
                {question.options.map((option) => {
                  const isSelected = selected.includes(option);
                  const isAtLimit = selected.length >= MAX_SELECTIONS && !isSelected;
                  return (
                    <button
                      key={option}
                      type="button"
                      className={`onboarding-option${isSelected ? ' selected' : ''}`}
                      onClick={() => toggleOption(option)}
                      aria-pressed={isSelected}
                      disabled={loading || isAtLimit}
                    >
                      <span>{option}</span>
                      <span className="onboarding-option-check" aria-hidden="true">
                        {isSelected && <Check size={14} />}
                      </span>
                    </button>
                  );
                })}
              </div>
              <p className="onboarding-selection-hint">
                Choose up to {MAX_SELECTIONS}; {selected.length} selected.
              </p>
            </MotionDiv>
          </AnimatePresence>
        </div>

        {message && <p className="onboarding-error" role="alert">{message}</p>}

        <div className="onboarding-actions">
          <button type="button" className="onboarding-skip" onClick={onSkip} disabled={loading}>
            Skip for now
          </button>
          <button
            type="button"
            className="onboarding-continue"
            onClick={handleContinue}
            disabled={loading}
          >
            {loading ? 'Saving...' : step === PREFERENCE_QUESTIONS.length - 1 ? 'Save my style' : 'Continue'}
            {!loading && <ArrowRight size={18} />}
          </button>
        </div>
      </div>
    </section>
  );
}
