# Auth fix notes (branch `auth-fix`)

The API had no server-side authentication. Login returned only a username, the
frontend kept it in `localStorage`, and every route trusted whatever
`username`, `user_id` or `upload_id` the client sent. Any client could read,
change or delete any user's data, and anyone could call the maintenance routes.

This branch adds JWT authentication, scopes every query to the token's user,
locks the maintenance routes to admins, fixes status codes, and adds a test
suite that proves each fix.

## Deploying this branch (read first)

- **Set `JWT_SECRET_KEY`** on the backend (Render) to a random value of at least
  32 bytes: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
  The app **refuses to start** without it, on purpose.
- Optionally set `JWT_EXPIRES_MINUTES` (default 60) and `ADMIN_USERNAMES`
  (comma-separated; empty means the maintenance routes are off for everyone).
- **Deploy the backend and frontend together.** The API contract changed: an
  old frontend cannot talk to the new backend (no token, `/history/<username>`
  is gone).
- Everyone who is currently "logged in" has a username but no token in
  `localStorage`, so they will be asked to log in once.
- **Rotate the Gemini and SerpAPI keys.** See fix 1.

## Commits

| Commit | Fix |
|---|---|
| `8cf108b` | Stop printing the SerpAPI key at import time |
| `c66b4b0` | Add failing auth and ownership tests |
| `2dac240` | Issue HS256 JWTs at login/signup and add `require_auth` |
| `65e9865` | Frontend: store the JWT and send it from a shared `apiFetch` helper |
| `e66a615` | Require auth and ownership on upload routes |
| `f194aee` | Require auth on `/profile` and scope it to the token user |
| `c969b35` | Require auth on `/interact` and `/search-ideas` |
| `c760cae` | Require auth on `/chatbot/query` and search only the caller's wardrobe |
| `888447c` | Make maintenance routes admin-only |
| `abc802d` | Fix status codes and stop returning exception text |

## Fixes

### 1. Secrets in code, logs and git

**Problem.** `api/routes/idea_search.py` ran `print(Config.SERPAPI_KEY)` on
import, writing the key to stdout and to the hosting provider's logs.

**Decision.** Removed the print. I checked the rest:

- `backend/.env` is **not tracked** in the current tree, and `.gitignore`
  covers `.env`, `api/.env` and `frontend/.env*` (`git check-ignore` confirms
  `backend/.env` is ignored by the `.env` rule). No `git rm --cached` was needed.
- **Real keys are in git history.** `backend/.env` with `GEMINI_API_KEY` and
  `SERPAPI_KEY` was committed in `19453ac`, `8b71c24` and `d53b46e`, and
  `origin` is on GitHub. Removing the file later does not remove it from
  history. **Rotate both keys.** Rewriting history (`git filter-repo`) needs a
  force-push and coordination, so I did not do it.
- Other places that print or hard-code sensitive values (not changed: outside this task):
  - `idea_search.py` prints each user's preference summary and generated query (user data in logs).
  - `frontend/src/pages/History.jsx` logs the username to the browser console.
  - `api/database.py` and `api/init_db.py` fall back to DB password `postgres` (and DB name `loga`) when env vars are missing. These are local-dev defaults, but production should never rely on them.
  - `idea_search.py` hard-codes `AMAZON_AFFILIATE_TAG`. It's a public affiliate id, not a secret, but it's config living in code.
  - `frontend/src/pages/Upload.jsx` falls back to cloud name `demo` and preset `unsigned_preset`.
  - `frontend/index.html` has the Google site-verification token. It's public by design.
- Two debug prints that logged usernames and full upload rows in `/history`
  were removed as part of rewriting that route.

**Verified.** `grep` for prints of config and keys: none left.

### 2. Tests first

**Problem.** There were no tests, so none of this could be proven.

**Decision.** pytest + Flask test client against **real PostgreSQL**, not a
mock. Ownership bugs live in `WHERE` clauses, and only real SQL tests those
honestly. `conftest.py` starts a throwaway cluster with `initdb`/`pg_ctl`
(trust auth, random port, 127.0.0.1 only) and loads `supabase_schema.sql`.
Gemini/SerpAPI are faked, all outbound HTTP is blocked, and `load_dotenv` is
disabled so the tests never read real keys. Attacker requests carry bob's
valid token **and** name alice in the body or query, the way the old API was
abused.

**Trade-off.** The tests need the PostgreSQL binaries (or a disposable
database in `TEST_DATABASE_URL`, which is **wiped** before every test). That's
heavier than mocks, but the tests check real behaviour.

**Verified.** On the code before the fixes (`c66b4b0`): **114 failed, 15
passed**. The failures were the real vulnerabilities, for example bob deleting
alice's upload (`200`), bob overwriting alice's profile
(`'HIJACKED' == 'ALICE-SIZE-S'`), and the chatbot returning alice's images to
bob. The 15 passes were guards that should already pass (wrong password is
401, admin can still run maintenance, and so on).

### 3. JWT issued at login and signup

**Problem.** Login proved nothing to later requests.

**Decision.** `api/security.py`:

- `/login` and `/signup` return `token` and `expires_in` alongside `user`.
- HS256 via PyJWT. Claims: `sub` (user id), `username`, `iat`, `exp`.
- The secret comes from `JWT_SECRET_KEY`; `create_app()` refuses to start if it
  is missing or shorter than 32 bytes.
- Expiry defaults to **60 minutes** (`JWT_EXPIRES_MINUTES`).
- Verification pins `algorithms=["HS256"]`, so `alg=none` and algorithm
  switching are rejected, and it requires `exp`, `iat` and `sub`.
- `require_auth` reads only `Authorization: Bearer <token>`. Tokens in the
  query string or body are ignored. The verified user is available as
  `get_current_user()`. CORS preflight (`OPTIONS`) passes without a token, as
  browsers require.
- Werkzeug password hashing is unchanged.

**Trade-offs.**

- **Bearer token in `localStorage` vs HttpOnly cookie.** `localStorage` is
  readable by any script on the page, so an XSS bug would leak the token. An
  HttpOnly `Secure` `SameSite` cookie hides the token from JavaScript but
  needs CSRF protection, `supports_credentials=True` CORS, and cross-site
  cookie setup between Vercel and Render (third-party cookie restrictions).
  The Bearer header was the smaller change for a split-domain deployment.
  Short expiry limits the damage.
- **Expiry.** 60 minutes, and no refresh token, so users log in again every
  hour. Shorter is safer but more annoying. Without refresh tokens, longer
  means a stolen token stays useful longer.
- **No refresh, no revocation.** Logout only clears the browser. A copied
  token keeps working until it expires. Rotating `JWT_SECRET_KEY` is the only
  "log everyone out" switch.
- **No database lookup per request.** A token for a deleted user stays valid
  until expiry. (There is no delete-account route today.)

**Verified.** `test_auth.py`: the token's claims and lifetime, a login token
accepted by a protected route, and 401 for: no token, missing `Bearer`, token
in the query string, garbage, wrong secret, expired, `alg=none`, HS512,
missing `exp`/`sub`/`username`, and a non-numeric `sub`. A short secret
prevents startup (checked by hand).

### 4. Every user-data route requires the token; queries are scoped to its user

**Problem.** Routes trusted client-supplied identity:

- `/history/<username>` let anyone read anyone's history.
- `/delete_upload` deleted any `upload_id`.
- `/toggle_favorite`, `/profile`, `/interact`, `/search-ideas`, `/classify`
  and `/chatbot/query` all took `username` or `user_id` from the request.

**Decision.** `@require_auth` on all of them. `username` and `user_id`
parameters were removed and the token user is used in every `WHERE` clause and
`INSERT`. Contract changes:

| Before | After |
|---|---|
| `GET /history/<username>` | `GET /history` (caller's own) |
| `GET /profile?username=x` | `GET /profile` |
| `username` / `user_id` in JSON bodies | ignored; identity comes from the token |
| `/delete_upload` deleted by id only | `DELETE ... WHERE id = %s AND username = %s`; 404 if nothing matched |

An upload that exists but belongs to someone else returns **404, the same as a
missing one**, so ids of other users' uploads can't be probed. The frontend
callers were updated in the same commits. `/chatbot/status` stays public as a
health check.

**Verified.** `test_ownership.py`: for history, delete, favorites, classify
(including the per-user duplicate check), suggestions, profile read/write,
interactions, idea-search personalization and logging, and the chatbot, bob's
requests never touch alice's rows, and alice can still use her own.

### 5. Maintenance routes are admin-only

**Problem.** `/check-duplicates` listed every user's image URLs,
`/clean-duplicates` deleted rows across all users, and
`/index-existing-images` spent Gemini quota on any user's images. None of them
required any identity.

**Decision.** `@require_admin`: a valid token whose username is in
`ADMIN_USERNAMES`. Non-admins get 403, and an empty list disables the routes
(fail closed). For `/index-existing-images`, the body's `username` is only the
**target** of the admin action, never the caller's identity.

**Trade-off.** Admins are identified by username, which is simple to configure.
If an admin account were ever deleted and the name re-registered, the new
account would be an admin. User ids or a `role` column would be stronger.

**Verified.** `test_admin.py`: 403 for regular users with nothing deleted or
analyzed, 403 for everyone when the list is empty, and admins can still run all
three routes.

### 6. Status codes and error bodies

**Problem.** A duplicate signup returned 500 with the raw database error. Bad
input crashed with `KeyError`/`AttributeError` and returned 500.
`/delete_upload` returned **200** on failure. Most routes put `str(e)` in the
response, and `/search-ideas` returned the provider's error text.

**Decision.**

- Duplicate signup is now 409, caught as `psycopg.errors.UniqueViolation`.
- Bad input is 400: a missing or non-JSON body, a body that isn't an object,
  missing or wrongly typed fields, an invalid `upload_id`, or a string longer
  than its `VARCHAR` column.
- Failures are 500 with a generic message, and the traceback is logged
  server-side with `logger.exception`.
- Connections are closed in `finally` on these paths.
- Helpers live in `api/request_utils.py`.

**Verified.** `test_errors.py` forces a database failure on every route and
checks for a 500 with no exception text. It also covers 400 for 24 bad-input
cases and no provider error text on 502. `test_auth.py` covers 409 and 400 for
signup and login. The three length-limit cases were added together with this
fix, not before it.

### 7. Frontend

**Decision.**

- `frontend/src/lib/api.js` has `saveSession`, `clearSession`,
  `hasValidSession` and `apiFetch()`.
- `apiFetch()` adds `Authorization: Bearer <token>`. On a 401 it clears the
  session and emits an event; `App.jsx` handles it by sending the user to
  `/login`.
- The signed-in state requires a non-expired token. The stored username is
  display-only. Reading `exp` in the browser is only a UX shortcut; the server
  is what verifies the token.
- Login and Signup still use plain `fetch`, because there a 401 means wrong
  credentials, not an expired session.
- Side effect: the session is read synchronously on first render, so
  reloading a protected page no longer bounces through `/login`.

**Verified.** `vite build` succeeds. `eslint` reports the same 3 errors as
`main` (unused `catch` variables in `IdeaSearch.jsx`, `Login.jsx` and
`Signup.jsx`) and nothing new. There are no frontend tests, and I did not
click through the UI in a browser.

## How I verified the whole branch

- `pytest`: **134 passed** (from 114 failed / 15 passed before the fixes).
- Frontend build passes; lint has no new problems.
- A manual curl run against the real app and a throwaway database, using the
  commands below. Every response matched the expected status.

### Running the tests

```bash
cd api
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash; use .venv/bin/activate on macOS/Linux
pip install -r requirements-dev.txt
pytest
```

The tests need PostgreSQL's `initdb` and `pg_ctl` on `PATH` (or set `PG_BIN`),
or `TEST_DATABASE_URL` pointing at a **disposable** database (it is wiped).

## How to test manually with curl

Start the API with `JWT_SECRET_KEY` set (and a database with
`supabase_schema.sql` applied), then:

```bash
API=http://localhost:5000
J='Content-Type: application/json'

# Sign up two users; signing up again is 409
curl -s -X POST $API/signup -H "$J" -d '{"username":"alice","password":"pw-alice-123"}'
curl -s -X POST $API/signup -H "$J" -d '{"username":"bob","password":"pw-bob-123"}'
curl -s -o /dev/null -w '%{http_code}\n' -X POST $API/signup -H "$J" -d '{"username":"alice","password":"x"}'   # 409

# Log in and keep the tokens
A=$(curl -s -X POST $API/login -H "$J" -d '{"username":"alice","password":"pw-alice-123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
B=$(curl -s -X POST $API/login -H "$J" -d '{"username":"bob","password":"pw-bob-123"}'   | python -c "import sys,json;print(json.load(sys.stdin)['token'])")

# No token -> 401; with a token you only see your own data
curl -s -w ' %{http_code}\n' $API/history                                   # 401
curl -s -w ' %{http_code}\n' $API/history -H "Authorization: Bearer $A"      # alice's uploads
curl -s -w ' %{http_code}\n' $API/history -H "Authorization: Bearer $B"      # [] for bob

# Bob cannot delete alice's upload, even when naming her (use one of alice's ids)
curl -s -w ' %{http_code}\n' -X POST $API/delete_upload -H "$J" -H "Authorization: Bearer $B" \
     -d '{"upload_id":1,"username":"alice"}'                                 # 404

# A username in the body is ignored: this saves bob's profile, not alice's
curl -s -X POST $API/profile -H "$J" -H "Authorization: Bearer $B" -d '{"username":"alice","sizes":"HIJACK"}'
curl -s $API/profile -H "Authorization: Bearer $A"                           # alice's sizes unchanged

# Admin routes: 403 unless the username is in ADMIN_USERNAMES
curl -s -w ' %{http_code}\n' $API/check-duplicates -H "Authorization: Bearer $B"   # 403

# A tampered token is rejected
curl -s -w ' %{http_code}\n' $API/history -H "Authorization: Bearer ${A%?}x"       # 401
```

On Windows PowerShell, call `curl.exe` (not the `curl` alias) or run these in Git Bash.

## What remains

Still open, and outside this task:

- **Rotate the leaked Gemini/SerpAPI keys**, and decide whether to rewrite git history (fix 1).
- **Refresh tokens and revocation.** Logout is client-side only. A token
  denylist (`jti`) or short access tokens plus refresh tokens would fix that.
- **HttpOnly cookie sessions**, if XSS exposure of `localStorage` becomes a concern (fix 3).
- **Rate limiting on `/login` and `/signup`.** Brute force and credential
  stuffing are not limited. Flask-Limiter is one option.
- **Username enumeration.** The 409 on signup reveals that a username exists
  (normal for signup). Login skips password hashing for unknown users, which
  is a timing difference.
- **SSRF in `/classify`.** The server downloads any `image_url` it's given.
  Restrict it to your Cloudinary domain.
- **The unsigned Cloudinary upload preset.** Anyone with the preset name can
  upload to the account.
- **`frontend/src/components/Chatbot.jsx` uses `<Helmet>` without importing
  it.** This was already the case before this branch. Rendering the chatbot
  page (or the Home chat modal) probably throws a ReferenceError. I left it
  unchanged as outside the task, and lint doesn't flag it.
- **The 3 lint errors that were already there** (unused `catch` variables).
- **`api/init_db.py` creates `users.password`, but the code uses
  `password_hash`.** The tests use `supabase_schema.sql`.
- **Race conditions:** check-then-insert duplicate detection in `/classify`,
  and the read-then-write in `/toggle_favorite`.
- **Admins are identified by username** rather than id or role (fix 5).
