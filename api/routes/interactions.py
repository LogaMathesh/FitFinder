import logging
from flask import Blueprint, request, jsonify
from database import get_connection
from request_utils import json_object, text_fields
from security import get_current_user, require_auth

logger = logging.getLogger(__name__)

interactions_bp = Blueprint('interactions_bp', __name__)

# Maximum lengths follow the user_interactions columns (None = TEXT).
ITEM_FIELDS = {'title': None, 'price': 100, 'link': None, 'thumbnail': None, 'source': 255}


@interactions_bp.route('/interact', methods=['POST', 'OPTIONS'])
@require_auth
def handle_interaction():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = json_object()
    if data is None:
        return jsonify({'error': 'Missing JSON body'}), 400

    username = get_current_user().username
    item = data.get('item', {})
    interaction_type = data.get('type') # 'like', 'dislike', 'save'

    if interaction_type not in ['like', 'dislike', 'save']:
        return jsonify({'error': 'Invalid interaction type'}), 400
    if not isinstance(item, dict):
        return jsonify({'error': 'item must be an object'}), 400

    fields, error = text_fields(item, ITEM_FIELDS)
    if error:
        return jsonify({'error': error}), 400

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO user_interactions (username, title, price, link, thumbnail, source, interaction_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, fields['title'], fields['price'], fields['link'], fields['thumbnail'],
              fields['source'], interaction_type))
        conn.commit()
        return jsonify({'message': f'Interaction {interaction_type} saved successfully'}), 200
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Saving interaction failed")
        return jsonify({'error': 'Failed to save interaction'}), 500
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()
