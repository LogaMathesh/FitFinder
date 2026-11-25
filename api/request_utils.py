"""Helpers for validating request input in route handlers."""
from flask import request


def json_object():
    """The request body if it is a JSON object, otherwise None (the caller answers 400).

    Uses silent=True so a missing or non-JSON body is a 400 from the route,
    not Flask's 415, and never an exception.
    """
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def parse_id(value):
    """A positive integer id from an int or a string of digits, otherwise None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str) and value.isdigit():
        return int(value) or None
    return None


def text_fields(data, limits):
    """Read optional text fields from a JSON object.

    `limits` maps field name to its maximum length (None for unlimited).
    Missing fields become "", null stays None. Returns (values, error_message).
    """
    values = {}
    for name, max_length in limits.items():
        value = data.get(name, "")
        if value is not None and not isinstance(value, str):
            return None, f"{name} must be a string"
        if max_length is not None and value is not None and len(value) > max_length:
            return None, f"{name} must be at most {max_length} characters"
        values[name] = value
    return values, None
