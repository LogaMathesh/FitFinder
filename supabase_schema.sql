-- Run this in the Supabase SQL Editor

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255),
    email VARCHAR(255),
    google_sub TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique
    ON users (google_sub) WHERE google_sub IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
    ON users (LOWER(email)) WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS oauth_login_codes (
    code_hash CHAR(64) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    onboarding_required BOOLEAN NOT NULL DEFAULT FALSE
);
ALTER TABLE oauth_login_codes
    ADD COLUMN IF NOT EXISTS onboarding_required BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS oauth_login_codes_expiry ON oauth_login_codes (expires_at);

-- 2. User Profiles
CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    gender VARCHAR(50),
    budget_level VARCHAR(100),
    sizes TEXT,
    style_preferences TEXT,
    onboarding_preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS onboarding_preferences JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 3. Uploads
CREATE TABLE IF NOT EXISTS uploads (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    image_path TEXT NOT NULL, -- This will store the Cloudinary URL
    position VARCHAR(100),
    style VARCHAR(100),
    color VARCHAR(100),
    md5_hash VARCHAR(32), -- Used to hash the Cloudinary URL to prevent duplicates
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    favorite BOOLEAN DEFAULT FALSE,
    gemini_metadata JSONB
);

-- 4. Search Logs (History)
CREATE TABLE IF NOT EXISTS search_logs (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) REFERENCES users(username) ON DELETE CASCADE,
    raw_prompt TEXT NOT NULL,
    generated_query TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. User Interactions
CREATE TABLE IF NOT EXISTS user_interactions (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) REFERENCES users(username) ON DELETE CASCADE,
    title TEXT,
    price VARCHAR(100),
    link TEXT,
    thumbnail TEXT,
    source VARCHAR(255),
    interaction_type VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. API Usage (rate limiting for paid endpoints: chatbot, idea search)
CREATE TABLE IF NOT EXISTS api_usage (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    action VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_usage_user_action_time ON api_usage (username, action, created_at);
