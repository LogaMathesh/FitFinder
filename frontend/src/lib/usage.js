import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { apiFetch } from './api';

// Rate-limit credits for the paid features. One store for the whole app
// (see components/UsageProvider.jsx), so moving between pages costs nothing.
//
// When the server is asked (GET /usage):
//   - once when the app loads or the user logs in,
//   - once when a used credit comes back (one timer for all actions),
//   - when the tab becomes visible again, at most once a minute.
// Chat and search replies carry the new count themselves, and the
// "next in N min" countdown is computed locally, so neither calls the server.
// Nothing runs while the tab is hidden.

export const ACTIONS = ['chatbot', 'idea_search'];
const VISIBLE_REFRESH_MIN_MS = 60_000;
const TICK_MS = 30_000;

function cacheKey(user) {
  return user ? `fitfinder_usage_${user}` : null;
}

function fromServer(u, at) {
  return {
    limit: u.limit,
    remaining: u.remaining,
    // Stored as an absolute time so a cached value stays meaningful later.
    resetAt: u.reset_in_seconds ? at + u.reset_in_seconds * 1000 : null,
  };
}

// The last known usage, shown at once while the server is asked again.
// A credit whose reset time has already passed is counted back in.
function readCache(key) {
  if (!key) return {};
  try {
    const saved = JSON.parse(localStorage.getItem(key)) || {};
    const now = Date.now();
    const result = {};
    for (const action of ACTIONS) {
      const u = saved[action];
      if (!u || typeof u.limit !== 'number' || typeof u.remaining !== 'number') continue;
      result[action] = u.resetAt && u.resetAt <= now
        ? { limit: u.limit, remaining: Math.min(u.limit, u.remaining + 1), resetAt: null }
        : { limit: u.limit, remaining: u.remaining, resetAt: u.resetAt || null };
    }
    return result;
  } catch {
    return {};
  }
}

function isVisible() {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden';
}

export const UsageContext = createContext({
  usage: {},
  now: 0,
  pending: false,
  applyUsage: () => {},
});

// State and timers behind UsageProvider.
export function useUsageStore(user) {
  const key = cacheKey(user);
  const [usage, setUsage] = useState(() => readCache(key));
  const [now, setNow] = useState(() => Date.now());
  const [visible, setVisible] = useState(isVisible);
  const [pending, setPending] = useState(Boolean(user));
  const lastFetchRef = useRef(0);
  const inFlightRef = useRef(false);

  useEffect(() => {
    if (!key) return;
    try {
      localStorage.setItem(key, JSON.stringify(usage));
    } catch {
      // Storage full or blocked: the counter still works, just without a cache.
    }
  }, [key, usage]);

  const applyUsage = useCallback((action, u) => {
    if (!u || typeof u.remaining !== 'number') return;
    const at = Date.now();
    setNow(at);
    setUsage((prev) => ({ ...prev, [action]: fromServer(u, at) }));
  }, []);

  const refresh = useCallback(async () => {
    if (!user || inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const res = await apiFetch('/usage');
      if (!res.ok) return;
      const data = await res.json();
      const at = Date.now();
      lastFetchRef.current = at;
      setNow(at);
      setUsage((prev) => {
        const next = { ...prev };
        for (const action of ACTIONS) {
          if (data[action]) next[action] = fromServer(data[action], at);
        }
        return next;
      });
    } catch {
      // Keep the last known value; the counter is informational only.
    } finally {
      inFlightRef.current = false;
      setPending(false);
    }
  }, [user]);

  // Once per app load / login.
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Pause while the tab is hidden; catch up when it is shown again.
  useEffect(() => {
    const onVisibilityChange = () => {
      const shown = isVisible();
      setVisible(shown);
      if (!shown) return;
      setNow(Date.now());
      if (Date.now() - lastFetchRef.current > VISIBLE_REFRESH_MIN_MS) refresh();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, [refresh]);

  // One countdown tick and one reload timer for all actions, only while a
  // credit is out and the tab is visible.
  const nextResetAt = ACTIONS
    .map((action) => usage[action]?.resetAt)
    .filter(Boolean)
    .reduce((min, t) => (min === null || t < min ? t : min), null);

  useEffect(() => {
    if (!visible || !nextResetAt) return undefined;
    const tick = setInterval(() => setNow(Date.now()), TICK_MS);
    const reload = setTimeout(refresh, Math.max(0, nextResetAt - Date.now()) + 1000);
    return () => {
      clearInterval(tick);
      clearTimeout(reload);
    };
  }, [visible, nextResetAt, refresh]);

  return { usage, now, pending, applyUsage };
}

// Credits for one action, for a page.
export function useUsage(action) {
  const { usage, now, pending, applyUsage } = useContext(UsageContext);
  const current = usage[action] || null;
  const secondsToReset = current?.resetAt
    ? Math.max(0, Math.ceil((current.resetAt - now) / 1000))
    : null;
  const apply = useCallback((u) => applyUsage(action, u), [applyUsage, action]);

  return {
    usage: current,
    secondsToReset,
    outOfCredits: current !== null && current.remaining <= 0,
    checking: current === null && pending,
    applyUsage: apply,
  };
}

export function shortWait(seconds) {
  return `${Math.max(1, Math.ceil((seconds || 0) / 60))} min`;
}

// CSS modifier for the credit counter: amber at 1 left, red at 0.
export function usageLevel(usage) {
  if (!usage) return '';
  if (usage.remaining <= 0) return 'empty';
  if (usage.remaining === 1) return 'low';
  return '';
}

export async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

// User-facing text for a request that did not succeed. `response` is null
// when the request never reached the server.
export function describeFailure(response, data) {
  if (!response) {
    return "Can't reach the server. Check your connection and try again.";
  }
  if (response.status === 429) {
    return data?.message || "You've reached the limit for now. Please try again later.";
  }
  if (response.status === 401) {
    return 'Your session expired. Please log in again.';
  }
  if (response.status === 400) {
    return "Please type what you're looking for.";
  }
  if (response.status >= 500) {
    return "Something went wrong on our side. This didn't use a credit, so please try again.";
  }
  return 'Something went wrong. Please try again.';
}
