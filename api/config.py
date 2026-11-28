import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
    JWT_EXPIRES_MINUTES = int(os.environ.get("JWT_EXPIRES_MINUTES", 60))
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")
    ADMIN_USERNAMES = [
        name.strip()
        for name in os.environ.get("ADMIN_USERNAMES", "").split(",")
        if name.strip()
    ]
    # Per-user limits on the endpoints that call paid APIs (Gemini, SerpAPI).
    RATE_LIMIT_WINDOW_MINUTES = int(os.environ.get("RATE_LIMIT_WINDOW_MINUTES", 30))
    CHATBOT_RATE_LIMIT = int(os.environ.get("CHATBOT_RATE_LIMIT", 5))
    IDEA_SEARCH_RATE_LIMIT = int(os.environ.get("IDEA_SEARCH_RATE_LIMIT", 2))
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 8 * 1024 * 1024))
    FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = ENV == "production"
    SESSION_COOKIE_SAMESITE = "Lax"
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", FRONTEND_URL).split(",")
        if origin.strip()
    ]
    SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
    CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")
    SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
    SERPAPI_LOCATION = os.environ.get("SERPAPI_LOCATION", "India")
    SERPAPI_COUNTRY = os.environ.get("SERPAPI_COUNTRY", "in")
    SERPAPI_GOOGLE_DOMAIN = os.environ.get("SERPAPI_GOOGLE_DOMAIN", "google.co.in")
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
