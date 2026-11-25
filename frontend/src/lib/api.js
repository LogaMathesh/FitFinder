export const API_BASE_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '');

const TOKEN_KEY = 'token';
// The username is kept for display only. The server takes identity from the token.
const DISPLAY_NAME_KEY = 'user';

export const UNAUTHORIZED_EVENT = 'fitfinder:unauthorized';

export function apiUrl(path) {
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalizedPath}`;
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getDisplayName() {
  return localStorage.getItem(DISPLAY_NAME_KEY);
}

export function saveSession({ token, user }) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(DISPLAY_NAME_KEY, user);
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(DISPLAY_NAME_KEY);
}

// Reads the expiry from the token payload. This is only a UX shortcut to skip
// requests that would fail anyway; the server is what verifies the token.
function tokenExpiresAt(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    const { exp } = JSON.parse(atob(payload));
    return typeof exp === 'number' ? exp * 1000 : 0;
  } catch {
    return 0;
  }
}

export function hasValidSession() {
  const token = getToken();
  return Boolean(token) && tokenExpiresAt(token) > Date.now();
}

// fetch() for API routes: adds the bearer token and, on 401, clears the
// session and tells the app to send the user to the login page.
export async function apiFetch(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = getToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const response = await fetch(apiUrl(path), { ...options, headers });

  if (response.status === 401) {
    clearSession();
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  }
  return response;
}
