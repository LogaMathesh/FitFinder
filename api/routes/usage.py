import logging

from flask import Blueprint, jsonify

import rate_limit
from security import get_current_user, require_auth

logger = logging.getLogger(__name__)

usage_bp = Blueprint('usage', __name__)


@usage_bp.route('/usage', methods=['GET'])
@require_auth
def usage():
    """Credits left for each rate-limited action. Reading this uses no credit."""
    try:
        return jsonify(rate_limit.get_all_usage(get_current_user().username)), 200
    except Exception:
        logger.exception("Usage lookup failed")
        return jsonify({'error': 'server_error', 'message': 'Could not load usage.'}), 500
