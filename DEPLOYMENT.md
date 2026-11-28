# Production Deployment

## Recommended Hosting

- Frontend: Vercel free tier.
- Backend: Render free tier for the Flask API. Render is the simpler choice here because it supports a persistent Python web service with a `Procfile` and environment variables without adapting Flask to serverless.
- Database: Supabase PostgreSQL free tier.
- Images: Cloudinary free tier with unsigned browser uploads and automatic quality/format optimization.

## Environment Variables

Paste backend variables into Render under Web Service > Environment:

- `SUPABASE_DB_URL`: Supabase Project Settings > Database > Connection string > Transaction pooler or Session pooler. Include `?sslmode=require`.
- `SUPABASE_URL`: Supabase Project Settings > API > Project URL.
- `SUPABASE_ANON_KEY`: Supabase Project Settings > API > anon public key.
- `CLOUDINARY_CLOUD_NAME`: Cloudinary Dashboard > Cloud name.
- `CLOUDINARY_API_KEY`: Cloudinary Dashboard > API key.
- `CLOUDINARY_API_SECRET`: Cloudinary Dashboard > API secret.
- `GEMINI_API_KEY`: Google AI Studio API key.
- `SERPAPI_KEY`: SerpAPI key, only if `/search-ideas` is enabled.
- `FRONTEND_URL`: Your Vercel URL, for example `https://fitfinder.vercel.app`.
- `CORS_ORIGINS`: Same Vercel URL plus local dev if needed: `https://fitfinder.vercel.app,http://localhost:5173`.
- `SECRET_KEY`: A random secret of at least 32 bytes, used to sign the OAuth state session cookie.
- `JWT_SECRET_KEY`: A separate random secret of at least 32 bytes for existing application JWTs.
- `GOOGLE_CLIENT_ID`: OAuth 2.0 client ID from Google Cloud Console.
- `GOOGLE_CLIENT_SECRET`: OAuth 2.0 client secret from Google Cloud Console.
- `GOOGLE_REDIRECT_URI`: Exact callback URI registered in Google Cloud Console, for example `https://fitfinder-api.onrender.com/auth/google/callback`.
- `RATE_LIMIT_WINDOW_MINUTES`, `CHATBOT_RATE_LIMIT`, `IDEA_SEARCH_RATE_LIMIT` (optional): per-user limits on the paid endpoints. Defaults: 5 chatbot queries and 2 idea searches per user per rolling 30 minutes.
- `DB_POOL_MAX_IDLE` (optional, default 4): database connections each worker keeps open for reuse, so requests skip the slow connect to Supabase. With 2 gunicorn workers that is at most 8 idle connections, well within the free tier.

Paste frontend variables into Vercel under Project Settings > Environment Variables:

- `VITE_API_URL`: Your Render backend URL, for example `https://fitfinder-api.onrender.com`.
- `VITE_CLOUDINARY_CLOUD_NAME`: Cloudinary Dashboard > Cloud name.
- `VITE_CLOUDINARY_UPLOAD_PRESET`: Cloudinary unsigned upload preset name.

## Supabase Setup

1. Create a Supabase project.
2. Open SQL Editor and run `supabase_schema.sql`.
3. Copy the pooled database connection string into `SUPABASE_DB_URL`.
   - **Existing database:** if the schema was created before rate limiting was added, run the `api_usage` block (section 6 of `supabase_schema.sql`) once in the SQL Editor. Without that table, `/chatbot/query`, `/search-ideas` and `/usage` return 500.
4. Use the anon key only for public frontend Supabase clients. This app currently uses Flask for database access, so keep database credentials on the backend only.
5. **Existing database:** re-run the updated `supabase_schema.sql` to add the nullable Google identity fields and one-time OAuth code table. It is safe to re-run on an existing schema.

## Google OAuth Setup

1. In Google Cloud Console, configure the OAuth consent screen and create a Web application OAuth client.
2. Add the exact backend callback URL as an Authorized redirect URI:
   - Local: `http://localhost:5000/auth/google/callback`
   - Render: `https://<your-render-service>.onrender.com/auth/google/callback`
3. Set `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI` on the backend. Keep the client secret and both server secrets private; never add them to Vercel or a `VITE_*` variable.
4. For local development, create `api/.env` with:

   ```dotenv
   FLASK_ENV=development
   SECRET_KEY=<random secret, at least 32 bytes>
   JWT_SECRET_KEY=<different random secret, at least 32 bytes>
   GOOGLE_CLIENT_ID=<Google OAuth client ID>
   GOOGLE_CLIENT_SECRET=<Google OAuth client secret>
   GOOGLE_REDIRECT_URI=http://localhost:5000/auth/google/callback
   FRONTEND_URL=http://localhost:5173
   CORS_ORIGINS=http://localhost:5173
   ```

   Configure the frontend's `VITE_API_URL` to `http://localhost:5000`.
5. In Render, set the same Google client credentials and the Render callback URI. Keep `FRONTEND_URL` set to the deployed frontend origin and include it in `CORS_ORIGINS`.

The callback uses Authlib's OpenID Connect state and ID-token validation. Only a verified Google email can link to an existing username/email match. The application JWT is returned only after the frontend exchanges a short-lived, single-use code; the JWT itself is not placed in a redirect URL.

## Cloudinary Setup

1. Create an unsigned upload preset.
2. Restrict the preset to images, set folder to `my_dress_app`, and enable transformations:
   - format: auto
   - quality: auto or eco
   - max dimensions around 1200 px
3. Put the preset name in `VITE_CLOUDINARY_UPLOAD_PRESET`.

## Render Backend

1. Create a new Render Web Service from the GitHub repo.
2. Root directory: `api`.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `gunicorn index:app --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120`.
5. Add the backend environment variables listed above.
6. Deploy and confirm `/chatbot/status` returns JSON.

## Vercel Frontend

1. Import the GitHub repo into Vercel.
2. Use the repository root as the project root.
3. Vercel will use `vercel.json` to build `frontend`.
4. Add the frontend environment variables listed above.
5. Deploy.
6. Copy the final Vercel domain back into Render as `FRONTEND_URL` and `CORS_ORIGINS`.

## Deployment Checklist

- No `.env`, `.venv`, `node_modules`, `dist`, local uploads, or model weights committed.
- `FLASK_DEBUG=0` in production.
- `CORS_ORIGINS` contains only trusted frontend domains.
- Supabase schema has `users.password_hash`, not `users.password`.
- Cloudinary upload preset is unsigned but restricted to image uploads.
- Gemini and SerpAPI keys exist only on the backend.
- `VITE_API_URL` points to the live backend.
- Upload flow works: browser uploads to Cloudinary, frontend sends `secure_url` to Flask, Flask analyzes with Gemini, result saves in Supabase, frontend renders result.
