"""Shared fixtures for the API test suite.

The suite runs against a real PostgreSQL database so that ownership checks
(the WHERE clauses) are tested with real SQL semantics and the real schema
from supabase_schema.sql.

Database selection, in order:
  1. TEST_DATABASE_URL, if set. That database is WIPED before every test, so
     point it at a disposable database, never at Supabase or a dev database.
  2. Otherwise a throwaway cluster is created with initdb/pg_ctl in a temp
     directory (trust auth, random port, 127.0.0.1 only) and removed afterwards.
     PostgreSQL's bin directory must be on PATH, or set PG_BIN.

External services (Gemini, SerpAPI, any outbound HTTP) are mocked or blocked.
"""
import base64
import datetime
import hashlib
import json
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

# --- Isolation from real credentials -------------------------------------
# This must run before any application module is imported. The app calls
# load_dotenv(), which would otherwise pull real keys (Gemini, SerpAPI,
# Supabase) from api/.env or the repo .env into the test process.
import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False

TEST_JWT_SECRET = "test-only-jwt-secret-not-used-anywhere-else-0123456789"
DEFAULT_PASSWORD = "correct-horse-battery"
SENSITIVE = "SENSITIVE-INTERNAL-DETAIL-42"

os.environ.update({
    "JWT_SECRET_KEY": TEST_JWT_SECRET,
    "JWT_EXPIRES_MINUTES": "60",
    "ADMIN_USERNAMES": "admin",
    "GEMINI_API_KEY": "",
    "SERPAPI_KEY": "",
    "CLOUDINARY_API_KEY": "",
    "CLOUDINARY_API_SECRET": "",
    "CORS_ORIGINS": "http://localhost:5173",
    # Until the test database URL is known, any accidental connection goes to
    # an unreachable port instead of a real local or hosted database.
    "SUPABASE_DB_URL": "",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "1",
})

API_DIR = Path(__file__).resolve().parents[1]
SCHEMA_FILE = API_DIR.parent / "supabase_schema.sql"
TABLES = ["user_interactions", "search_logs", "uploads", "user_profiles", "users"]


# --- Database --------------------------------------------------------------
def _pg_tool(name):
    pg_bin = os.environ.get("PG_BIN")
    if pg_bin:
        for candidate in (Path(pg_bin) / name, Path(pg_bin) / f"{name}.exe"):
            if candidate.exists():
                return str(candidate)
    return shutil.which(name)


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def database_url(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        yield url
        return

    initdb, pg_ctl = _pg_tool("initdb"), _pg_tool("pg_ctl")
    if not initdb or not pg_ctl:
        pytest.exit(
            "PostgreSQL binaries (initdb, pg_ctl) were not found. Put PostgreSQL's "
            "bin directory on PATH, set PG_BIN, or set TEST_DATABASE_URL to a "
            "disposable database.",
            returncode=2,
        )

    base = tmp_path_factory.mktemp("pg")
    datadir, logfile = base / "data", base / "postgres.log"
    subprocess.run(
        [initdb, "-D", str(datadir), "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    port = _free_port()
    # stdout/stderr go to DEVNULL: on Windows the server inherits captured pipes
    # and subprocess.run would never return.
    started = subprocess.run(
        [pg_ctl, "-D", str(datadir), "-l", str(logfile), "-w", "-t", "60",
         "-o", f"-p {port} -c listen_addresses=127.0.0.1", "start"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if started.returncode != 0:
        log = logfile.read_text(errors="replace") if logfile.exists() else ""
        pytest.exit(f"Could not start the test PostgreSQL cluster:\n{log}", returncode=2)
    try:
        yield f"postgresql://postgres@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            [pg_ctl, "-D", str(datadir), "-m", "immediate", "-w", "stop"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


@pytest.fixture(scope="session")
def app_modules(database_url):
    """Import the application only after the test database URL is known."""
    os.environ["SUPABASE_DB_URL"] = database_url

    import psycopg
    import database
    import index
    from routes import auth, chatbot, idea_search, interactions, maintenance, profile, uploads

    assert database.DB_URL == database_url, "the app must use the test database"

    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(SCHEMA_FILE.read_text())

    return SimpleNamespace(
        index=index, auth=auth, chatbot=chatbot, idea_search=idea_search,
        interactions=interactions, maintenance=maintenance, profile=profile, uploads=uploads,
    )


class DBHelper:
    """Direct database access for arranging and checking test state."""

    def __init__(self, url):
        self.url = url

    def query(self, sql, params=()):
        import psycopg

        with psycopg.connect(self.url, autocommit=True) as conn:
            cur = conn.execute(sql, params)
            return cur.fetchall() if cur.description else []

    def reset(self):
        self.query(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE")

    def create_user(self, username, password=DEFAULT_PASSWORD):
        from werkzeug.security import generate_password_hash

        return self.query(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, generate_password_hash(password)),
        )[0][0]

    def create_upload(self, username, image_path, *, style="casual", position="upper",
                      color="black", favorite=False, analyzed=True, md5_hash=None):
        md5_hash = md5_hash or hashlib.md5(image_path.encode("utf-8")).hexdigest()
        meta = json.dumps({"style": style}) if analyzed else None
        return self.query(
            """INSERT INTO uploads (username, image_path, position, style, color, md5_hash,
                                    favorite, gemini_metadata)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (username, image_path, position, style, color, md5_hash, favorite, meta),
        )[0][0]

    def upload(self, upload_id):
        rows = self.query(
            "SELECT id, username, image_path, favorite, gemini_metadata FROM uploads WHERE id = %s",
            (upload_id,),
        )
        if not rows:
            return None
        keys = ("id", "username", "image_path", "favorite", "gemini_metadata")
        return dict(zip(keys, rows[0]))

    def uploads_of(self, username):
        return [r[0] for r in self.query(
            "SELECT image_path FROM uploads WHERE username = %s ORDER BY id", (username,))]

    def create_profile(self, username, **fields):
        self.query(
            """INSERT INTO user_profiles (username, gender, budget_level, sizes, style_preferences)
               VALUES (%s, %s, %s, %s, %s)""",
            (username, fields.get("gender", ""), fields.get("budget_level", ""),
             fields.get("sizes", ""), fields.get("style_preferences", "")),
        )

    def profile(self, username):
        rows = self.query(
            "SELECT gender, budget_level, sizes, style_preferences FROM user_profiles WHERE username = %s",
            (username,),
        )
        if not rows:
            return None
        return dict(zip(("gender", "budget_level", "sizes", "style_preferences"), rows[0]))

    def create_interaction(self, username, title, interaction_type="like"):
        self.query(
            "INSERT INTO user_interactions (username, title, interaction_type) VALUES (%s, %s, %s)",
            (username, title, interaction_type),
        )

    def interactions_of(self, username):
        return self.query(
            "SELECT title, interaction_type FROM user_interactions WHERE username = %s ORDER BY id",
            (username,),
        )

    def search_logs_of(self, username):
        return self.query(
            "SELECT raw_prompt, generated_query FROM search_logs WHERE username = %s ORDER BY id",
            (username,),
        )


@pytest.fixture
def db(app_modules, database_url):
    test_db = DBHelper(database_url)
    test_db.reset()
    return test_db


# --- App and client --------------------------------------------------------
@pytest.fixture
def app(app_modules, db):
    flask_app = app_modules.index.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


# --- Tokens and users ------------------------------------------------------
def _b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture
def make_token():
    """Mint a token the way the server is expected to: HS256, sub=user id."""
    import jwt

    def _make(user_id, username, *, secret=TEST_JWT_SECRET, algorithm="HS256",
              expires_in=datetime.timedelta(minutes=15), extra=None, drop=()):
        now = datetime.datetime.now(datetime.timezone.utc)
        claims = {"sub": str(user_id), "username": username, "iat": now, "exp": now + expires_in}
        claims.update(extra or {})
        for name in drop:
            claims.pop(name, None)
        return jwt.encode(claims, secret, algorithm=algorithm)

    return _make


@pytest.fixture
def unsigned_token():
    """A token using alg=none, which the server must reject."""
    def _make(user_id, username):
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        header = _b64url(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        payload = _b64url(json.dumps(
            {"sub": str(user_id), "username": username, "iat": now, "exp": now + 900}).encode())
        return f"{header}.{payload}."

    return _make


@dataclass
class AuthUser:
    id: int
    username: str
    password: str
    token: str
    headers: dict = field(default_factory=dict)


@pytest.fixture
def make_user(db, make_token):
    def _make(username, password=DEFAULT_PASSWORD):
        user_id = db.create_user(username, password)
        token = make_token(user_id, username)
        return AuthUser(user_id, username, password, token, {"Authorization": f"Bearer {token}"})

    return _make


@pytest.fixture
def alice(make_user):
    return make_user("alice")


@pytest.fixture
def bob(make_user):
    return make_user("bob")


@pytest.fixture
def admin(make_user):
    return make_user("admin")


# --- External services -----------------------------------------------------
FAKE_METADATA = {
    "category": "upper", "style": "formal", "primary_color": "navy",
    "secondary_colors": [], "fit": "slim", "pattern": "solid", "occasion": ["office"],
    "season": ["all"], "gender": "unisex", "confidence": 0.9, "description": "Test item",
}


@pytest.fixture(autouse=True)
def external_services(monkeypatch, app_modules):
    """Replace Gemini/SerpAPI with fakes and block all outbound HTTP."""
    import google.generativeai as genai
    import requests

    calls = SimpleNamespace(analyzed=[], matched=[])

    def fake_analyze(image_url):
        calls.analyzed.append(image_url)
        return dict(FAKE_METADATA)

    def fake_match(query, wardrobe_items):
        calls.matched.append(wardrobe_items)
        return [item["url"] for item in wardrobe_items][:3]

    def no_network(*args, **kwargs):
        raise RuntimeError("Network access is disabled in tests")

    monkeypatch.setattr(app_modules.uploads, "analyze_dress_image_url", fake_analyze)
    monkeypatch.setattr(app_modules.maintenance, "analyze_dress_image_url", fake_analyze)
    monkeypatch.setattr(app_modules.chatbot, "suggest_matching_items", fake_match)
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(genai, "GenerativeModel", no_network)
    return calls
