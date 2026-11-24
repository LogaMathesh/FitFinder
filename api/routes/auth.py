import logging

import psycopg
from flask import Blueprint, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_connection
from request_utils import json_object
from security import create_access_token, token_lifetime_seconds

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth_bp', __name__)

USERNAME_MAX_LENGTH = 255  # users.username is VARCHAR(255)


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

        if result and check_password_hash(result[1], password):
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
