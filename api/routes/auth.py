import hashlib
import logging
import secrets
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import psycopg
import requests
from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.flask_client import OAuth
from authlib.jose.errors import JoseError
from flask import Blueprint, current_app, jsonify, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection
from request_utils import json_object
from security import create_access_token, token_lifetime_seconds

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth_bp', __name__)
oauth = OAuth()

USERNAME_MAX_LENGTH = 255  # users.username is VARCHAR(255)
OAUTH_CODE_LIFETIME = timedelta(minutes=2)


def init_oauth(app):
    """Configure Authlib only when both Google credentials are supplied."""
    client_id = app.config.get("GOOGLE_CLIENT_ID")
    client_secret = app.config.get("GOOGLE_CLIENT_SECRET")
    if bool(client_id) != bool(client_secret):
        raise RuntimeError("Both GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set.")
    if not client_id:
        return
    secret_key = app.config.get("SECRET_KEY") or ""
    if len(secret_key.encode("utf-8")) < 32 or not app.config.get("GOOGLE_REDIRECT_URI"):
        raise RuntimeError(
            "Google login requires a SECRET_KEY of at least 32 bytes and GOOGLE_REDIRECT_URI."
        )

    oauth.init_app(app)
    oauth.register(
        name="google",
        client_id=client_id,
        client_secret=client_secret,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _google_login_configured():
    return all((
        current_app.config.get("GOOGLE_CLIENT_ID"),
        current_app.config.get("GOOGLE_CLIENT_SECRET"),
        current_app.config.get("GOOGLE_REDIRECT_URI"),
        current_app.config.get("SECRET_KEY"),
    ))


def _frontend_login_redirect(**fragment_values):
    login_url = f'{current_app.config["FRONTEND_URL"].rstrip("/")}/login'
    response = redirect(f"{login_url}#{urlencode(fragment_values)}")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _create_oauth_code(user_id):
    code = secrets.token_urlsafe(32)
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + OAUTH_CODE_LIFETIME

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM oauth_login_codes WHERE expires_at <= now()")
            cur.execute(
                """INSERT INTO oauth_login_codes (code_hash, user_id, expires_at)
                   VALUES (%s, %s, %s)""",
                (code_hash, user_id, expires_at),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("Could not create OAuth login code")
        raise
    finally:
        conn.close()
    return code


def _resolve_google_user(sub, email):
    """Return the existing app user, linking only an exact verified email."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username FROM users WHERE google_sub = %s",
                (sub,),
            )
            linked_user = cur.fetchone()
            if linked_user:
                conn.commit()
                return linked_user

            cur.execute(
                """SELECT id, username, google_sub
                   FROM users
                   WHERE LOWER(email) = %s OR LOWER(username) = %s
                   FOR UPDATE""",
                (email, email),
            )
            matches = cur.fetchall()
            if len(matches) > 1:
                conn.rollback()
                return None
            if matches:
                user_id, username, linked_sub = matches[0]
                if linked_sub:
                    conn.rollback()
                    return None
                cur.execute(
                    """UPDATE users
                       SET email = %s, google_sub = %s
                       WHERE id = %s AND google_sub IS NULL
                       RETURNING id, username""",
                    (email, sub, user_id),
                )
                linked_user = cur.fetchone()
                if not linked_user:
                    conn.rollback()
                    return None
                conn.commit()
                return linked_user

            if len(email) > USERNAME_MAX_LENGTH:
                conn.rollback()
                return None
            cur.execute(
                """INSERT INTO users (username, password_hash, email, google_sub)
                   VALUES (%s, NULL, %s, %s)
                   RETURNING id, username""",
                (email, email, sub),
            )
            created_user = cur.fetchone()
        conn.commit()
        return created_user
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        return None
    except Exception:
        conn.rollback()
        logger.exception("Could not resolve Google user")
        raise
    finally:
        conn.close()


def _read_credentials():
    """(username, password) from the JSON body, or None if missing or malformed."""
    data = json_object()
    if data is None:
        return None
    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    if not username.strip() or not password or len(username) > USERNAME_MAX_LENGTH:
        return None
    return username, password


@auth_bp.route('/signup', methods=['POST'])
def signup():
    credentials = _read_credentials()
    if credentials is None:
        return jsonify({"error": "Username and password are required"}), 400
    username, password = credentials

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        password_hash = generate_password_hash(password)
        cur.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id",
            (username, password_hash),
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({
            "message": "Signup successful",
            "user": username,
            "token": create_access_token(user_id, username),
            "expires_in": token_lifetime_seconds(),
        }), 200
    except psycopg.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "Username is already taken"}), 409
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Signup failed")
        return jsonify({"error": "Signup failed. Please try again."}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@auth_bp.route('/login', methods=['POST'])
def login():
    credentials = _read_credentials()
    if credentials is None:
        return jsonify({"error": "Username and password are required"}), 400
    username, password = credentials

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, password_hash FROM users WHERE username = %s", (username,))
        result = cur.fetchone()

        if result and result[1] and check_password_hash(result[1], password):
            return jsonify({
                "message": "Login successful",
                "user": username,
                "token": create_access_token(result[0], username),
                "expires_in": token_lifetime_seconds(),
            }), 200
        else:
            return jsonify({"error": "Invalid credentials"}), 401
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Login failed")
        return jsonify({"error": "Login failed. Please try again."}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


@auth_bp.route('/auth/google', methods=['GET'])
def google_login():
    if not _google_login_configured():
        return _frontend_login_redirect(oauth_error="not_configured")
    try:
        response = oauth.google.authorize_redirect(current_app.config["GOOGLE_REDIRECT_URI"])
    except (OAuthError, JoseError, requests.RequestException):
        logger.exception("Could not start Google OAuth")
        return _frontend_login_redirect(oauth_error="google_auth_failed")
    response.headers["Cache-Control"] = "no-store"
    return response


@auth_bp.route('/auth/google/callback', methods=['GET'])
def google_callback():
    if not _google_login_configured():
        return _frontend_login_redirect(oauth_error="not_configured")

    try:
        token = oauth.google.authorize_access_token()
    except (OAuthError, JoseError, requests.RequestException):
        logger.info("Google OAuth authorization was rejected or failed")
        return _frontend_login_redirect(oauth_error="google_auth_failed")

    userinfo = token.get("userinfo") if isinstance(token, Mapping) else None
    if not isinstance(userinfo, Mapping):
        logger.warning("Google OAuth response did not contain verified OIDC userinfo")
        return _frontend_login_redirect(oauth_error="google_auth_failed")

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    if (
        not isinstance(sub, str) or not sub.strip()
        or not isinstance(email, str) or not email.strip()
        or userinfo.get("email_verified") is not True
    ):
        logger.warning("Google OIDC identity is missing a verified subject or email")
        return _frontend_login_redirect(oauth_error="google_auth_failed")

    email = email.strip().lower()
    if len(email) > USERNAME_MAX_LENGTH:
        return _frontend_login_redirect(oauth_error="account_conflict")
    try:
        user = _resolve_google_user(sub.strip(), email)
        if not user:
            return _frontend_login_redirect(oauth_error="account_conflict")
        code = _create_oauth_code(user[0])
    except psycopg.Error:
        return _frontend_login_redirect(oauth_error="server_error")

    return _frontend_login_redirect(oauth_code=code)


@auth_bp.route('/auth/google/exchange', methods=['POST'])
def exchange_google_code():
    data = json_object()
    code = data.get("code") if data else None
    if not isinstance(code, str) or not code or len(code) > 128:
        return jsonify({"error": "Invalid or expired Google login code"}), 400

    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM oauth_login_codes
                   WHERE code_hash = %s AND expires_at > now()
                   RETURNING user_id""",
                (code_hash,),
            )
            result = cur.fetchone()
            if not result:
                conn.rollback()
                return jsonify({"error": "Invalid or expired Google login code"}), 400
            user_id = result[0]
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                conn.rollback()
                return jsonify({"error": "Invalid or expired Google login code"}), 400
        conn.commit()
        username = user[0]
        response = jsonify({
            "message": "Login successful",
            "user": username,
            "token": create_access_token(user_id, username),
            "expires_in": token_lifetime_seconds(),
        })
        response.headers["Cache-Control"] = "no-store"
        return response, 200
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Google login code exchange failed")
        return jsonify({"error": "Google login failed. Please try again."}), 500
    finally:
        if conn:
            conn.close()
