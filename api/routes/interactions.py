from flask import Blueprint, request, jsonify
from database import get_connection
from security import get_current_user, require_auth

interactions_bp = Blueprint('interactions_bp', __name__)

@interactions_bp.route('/interact', methods=['POST', 'OPTIONS'])
@require_auth
def handle_interaction():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing JSON body'}), 400

    username = get_current_user().username
    item = data.get('item', {})
    interaction_type = data.get('type') # 'like', 'dislike', 'save'

    if interaction_type not in ['like', 'dislike', 'save']:
        return jsonify({'error': 'Invalid interaction type'}), 400

    title = item.get('title', '')
    price = item.get('price', '')
    link = item.get('link', '')
    thumbnail = item.get('thumbnail', '')
    source = item.get('source', '')

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO user_interactions (username, title, price, link, thumbnail, source, interaction_type)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username, title, price, link, thumbnail, source, interaction_type))
        conn.commit()
        return jsonify({'message': f'Interaction {interaction_type} saved successfully'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'error': 'Failed to save interaction', 'details': str(e)}), 500
    finally:
        cur.close()
        conn.close()
