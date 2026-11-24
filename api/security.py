"""JWT access tokens and the require_auth / require_admin decorators.

Identity comes only from a verified "Authorization: Bearer <token>" header.
Routes must never take a username or user id from the body, URL or query
string to decide whose data to read or change.
"""
import datetime
import functools
import logging
from dataclasses import dataclass

import jwt
from flask import current_app, g, jsonify, request

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
MIN_SECRET_LENGTH = 32  # bytes; RFC 7518 requires a key at least as long as the HS256 output


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str


def validate_jwt_config(config):
    """Fail at startup instead of issuing or accepting tokens with a weak setup."""
    secret = config.get("JWT_SECRET_KEY") or ""
    if len(secret.encode("utf-8")) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            f"JWT_SECRET_KEY must be set to a random value of at least {MIN_SECRET_LENGTH} bytes."
        )
    if int(config.get("JWT_EXPIRES_MINUTES", 0)) <= 0:
        raise RuntimeError("JWT_EXPIRES_MINUTES must be a positive number of minutes.")


def create_access_token(user_id, username):
    now = datetime.datetime.now(datetime.timezone.utc)
    lifetime = datetime.timedelta(minutes=int(current_app.config["JWT_EXPIRES_MINUTES"]))
    claims = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(claims, current_app.config["JWT_SECRET_KEY"], algorithm=ALGORITHM)


def token_lifetime_seconds():
    return int(current_app.config["JWT_EXPIRES_MINUTES"]) * 60


def _unauthorized(message):
    response = jsonify({"error": "unauthorized", "message": message})
    response.status_code = 401
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


def _user_from_request():
    """Return the CurrentUser for a valid bearer token, or an error message."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return None, "Authentication required."

    try:
        claims = jwt.decode(
            token,
            current_app.config["JWT_SECRET_KEY"],
            algorithms=[ALGORITHM],  # never trust the token's own "alg" header
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        return None, "Session expired. Please log in again."
    except jwt.InvalidTokenError:
        return None, "Invalid token."

    username = claims.get("username")
    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError):
        return None, "Invalid token."
    if not isinstance(username, str) or not username:
        return None, "Invalid token."

    return CurrentUser(id=user_id, username=username), None


def require_auth(view):
    """Reject the request with 401 unless it carries a valid access token.

    The verified user is available to the view as get_current_user().
    """
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        # CORS preflight requests never carry credentials; let them through.
        if request.method == "OPTIONS":
            return current_app.make_default_options_response()

        user, error = _user_from_request()
        if error:
            return _unauthorized(error)
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper


def get_current_user():
    return g.current_user


def require_admin(view):
    """require_auth, plus the token's username must be listed in ADMIN_USERNAMES.

    An empty ADMIN_USERNAMES means nobody is an admin (the routes are disabled).
    """
    @functools.wraps(view)
    def check_admin(*args, **kwargs):
        if get_current_user().username not in current_app.config.get("ADMIN_USERNAMES", []):
            return jsonify({"error": "forbidden", "message": "Admin access required."}), 403
        return view(*args, **kwargs)

    return require_auth(check_admin)
