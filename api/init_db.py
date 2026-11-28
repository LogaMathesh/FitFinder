import os
import psycopg

def init_db():
    print("Connecting to the database...")
    conn = psycopg.connect(
        dbname=os.environ.get("DB_NAME", "loga"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postgres"),
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
    )
    cur = conn.cursor()

    print("Creating tables...")
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255),
            email VARCHAR(255),
            google_sub TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    cur.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub TEXT")
    cur.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS users_google_sub_unique
           ON users (google_sub) WHERE google_sub IS NOT NULL"""
    )
    cur.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS users_email_unique
           ON users (LOWER(email)) WHERE email IS NOT NULL"""
    )
    cur.execute('''
        CREATE TABLE IF NOT EXISTS oauth_login_codes (
            code_hash CHAR(64) PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL
        )
    ''')
    cur.execute(
        "CREATE INDEX IF NOT EXISTS oauth_login_codes_expiry ON oauth_login_codes (expires_at)"
    )

    cur.execute('''
        CREATE TABLE IF NOT EXISTS uploads (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            image_path TEXT NOT NULL,
            position VARCHAR(255),  
            style VARCHAR(255),
            color VARCHAR(255),
            md5_hash VARCHAR(255),
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            favorite BOOLEAN DEFAULT FALSE,
            gemini_metadata JSONB
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL REFERENCES users(username) ON DELETE CASCADE,
            gender VARCHAR(50),
            budget_level VARCHAR(100),
            sizes TEXT,
            style_preferences TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS search_logs (
            id SERIAL PRIMARY KEY,
            username VARCHAR(255) REFERENCES users(username) ON DELETE CASCADE,
            raw_prompt TEXT NOT NULL,
            generated_query TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cur.execute('''
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
        )
    ''')

    conn.commit()
    cur.close()
    conn.close()
    print("Database initialization complete! Tables 'users' and 'uploads' have been created.")

if __name__ == "__main__":
    init_db()
