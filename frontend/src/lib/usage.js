import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from './api';

// Tracks the rate-limit credits for one action ("chatbot" or "idea_search").
// The server is the source of truth: GET /usage on mount, then the `usage`
// object that every 200 and 429 response carries. A 400 or 5xx leaves the
// count unchanged (5xx calls are refunded), so nothing needs updating then.
export function useUsage(action) {
  const [usage, setUsage] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  const applyUsage = useCallback((u) => {
    if (!u || typeof u.remaining !== 'number') return;
    const at = Date.now();
    setNow(at);
    setUsage({
      limit: u.limit,
      remaining: u.remaining,
      resetAt: u.reset_in_seconds ? at + u.reset_in_seconds * 1000 : null,
    });
  }, []);

  const refresh = useCallback(async () => {
    try {
      const res = await apiFetch('/usage');
      if (!res.ok) return;
      const data = await res.json();
      applyUsage(data[action]);
    } catch {
      // Leave the last known value; the counter is informational only.
    }
  }, [action, applyUsage]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Keep "next in N min" current, and re-read the count when a credit comes back.
  const resetAt = usage?.resetAt;
  useEffect(() => {
    if (!resetAt) return undefined;
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    const reload = setTimeout(refresh, Math.max(0, resetAt - Date.now()) + 1000);
    return () => {
      clearInterval(tick);
      clearTimeout(reload);
    };
  }, [resetAt, refresh]);

  const secondsToReset = resetAt ? Math.max(0, Math.ceil((resetAt - now) / 1000)) : null;
  const outOfCredits = usage !== null && usage.remaining <= 0;

  return { usage, secondsToReset, outOfCredits, applyUsage };
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
