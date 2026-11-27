"""Per-user rate limits for the endpoints that call paid APIs.

Each allowed call is one row in api_usage. A call is allowed while the user
has fewer than `limit` rows for that action in the last window (a sliding
window). The count lives in Postgres, not in memory, because gunicorn runs
several workers and the host restarts the process when it sleeps.

Credits are only used once a request has passed auth and input validation
(routes call consume() after validating), and a call that ends in a 5xx is
refunded by refund_on_server_error().
"""
import logging
import math

from flask import current_app, g, jsonify

from database import get_connection
from security import get_current_user

logger = logging.getLogger(__name__)

# action -> (config key holding the limit, plural noun used in messages)
ACTIONS = {
    "chatbot": ("CHATBOT_RATE_LIMIT", "chats"),
    "idea_search": ("IDEA_SEARCH_RATE_LIMIT", "idea searches"),
}


def _limits(action):
    config_key, noun = ACTIONS[action]
    limit = int(current_app.config[config_key])
    window_minutes = int(current_app.config["RATE_LIMIT_WINDOW_MINUTES"])
    return limit, window_minutes, noun


def _usage(cur, username, action, limit, window_minutes):
    """Prune expired rows, then describe what is left in the window."""
    cur.execute(
        """DELETE FROM api_usage
           WHERE username = %s AND action = %s
             AND created_at <= now() - make_interval(mins => %s)""",
        (username, action, window_minutes),
    )
    cur.execute(
        """SELECT count(*),
                  EXTRACT(EPOCH FROM (min(created_at) + make_interval(mins => %s) - now()))
           FROM api_usage WHERE username = %s AND action = %s""",
        (window_minutes, username, action),
    )
    used, seconds_left = cur.fetchone()
    return _usage_dict(limit, used, seconds_left)


def _usage_dict(limit, used, seconds_left):
    reset_in = None
    if used and seconds_left is not None:
        reset_in = max(1, math.ceil(float(seconds_left)))
    return {
        "limit": limit,
        "used": used,
        "remaining": max(0, limit - used),
        "reset_in_seconds": reset_in,
    }


def format_wait(seconds):
    minutes = max(1, math.ceil(seconds / 60))
    return f"{minutes} minute" if minutes == 1 else f"{minutes} minutes"


def _server_error():
    return jsonify({"error": "server_error", "message": "Something went wrong. Please try again."}), 500


def consume(action):
    """Use one credit of `action` for the current user.

    Returns (None, usage) when the call may go ahead, or (response, usage) when
    it must not: a 429 when the limit is reached, a 500 if the check failed.
    """
    username = get_current_user().username
    limit, window_minutes, noun = _limits(action)

    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            # Serialise concurrent requests for the same user and action, so two
            # requests arriving together cannot both take the last credit.
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{username}:{action}",))
            usage = _usage(cur, username, action, limit, window_minutes)

            if usage["used"] >= limit:
                conn.commit()  # keep the prune
                retry_after = usage["reset_in_seconds"] or 1
                response = jsonify({
                    "error": "rate_limited",
                    "message": f"You've used all {limit} {noun} for now. "
                               f"Try again in {format_wait(retry_after)}.",
                    "retry_after_seconds": retry_after,
                    "usage": usage,
                })
                response.status_code = 429
                response.headers["Retry-After"] = str(retry_after)
                return response, usage

            cur.execute(
                "INSERT INTO api_usage (username, action) VALUES (%s, %s) RETURNING id",
                (username, action),
            )
            g.rate_limit_usage_id = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Rate limit check failed for %s", action)
        return _server_error(), None

    if usage["used"] == 0:
        usage["reset_in_seconds"] = window_minutes * 60
    usage["used"] += 1
    usage["remaining"] = max(0, limit - usage["used"])
    return None, usage


def get_all_usage(username):
    """Current usage of every action for one user. Uses no credit.

    One read-only query for all actions; expired rows are simply not counted
    here (consume() prunes them).
    """
    window_minutes = int(current_app.config["RATE_LIMIT_WINDOW_MINUTES"])
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """SELECT action, count(*),
                      EXTRACT(EPOCH FROM (min(created_at) + make_interval(mins => %s) - now()))
               FROM api_usage
               WHERE username = %s AND created_at > now() - make_interval(mins => %s)
               GROUP BY action""",
            (window_minutes, username, window_minutes),
        )
        rows = {action: (used, seconds_left) for action, used, seconds_left in cur.fetchall()}
    finally:
        conn.close()

    result = {}
    for action in ACTIONS:
        limit, _, _ = _limits(action)
        used, seconds_left = rows.get(action, (0, None))
        result[action] = _usage_dict(limit, used, seconds_left)
    return result


def refund_on_server_error(response):
    """after_request hook: give the credit back if the call failed on our side."""
    usage_id = g.pop("rate_limit_usage_id", None)
    if usage_id is None or response.status_code < 500:
        return response
    try:
        conn = get_connection()
        try:
            conn.execute("DELETE FROM api_usage WHERE id = %s", (usage_id,))
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("Could not refund rate-limit credit %s", usage_id)
    return response
