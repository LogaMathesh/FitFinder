import logging
from flask import Blueprint, request, jsonify
from database import get_connection
from request_utils import json_object, text_fields
from security import get_current_user, require_auth

logger = logging.getLogger(__name__)

profile_bp = Blueprint('profile_bp', __name__)

# Maximum lengths follow the user_profiles columns (None = TEXT).
PROFILE_FIELDS = {'gender': 50, 'budget_level': 100, 'sizes': None, 'style_preferences': None}


@profile_bp.route('/profile', methods=['GET', 'POST', 'OPTIONS'])
@require_auth
def handle_profile():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    username = get_current_user().username

    if request.method == 'GET':
        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT gender, budget_level, sizes, style_preferences
                FROM user_profiles WHERE username = %s
            """, (username,))
            row = cur.fetchone()

            if row:
                return jsonify({
                    'gender': row[0] or '',
                    'budget_level': row[1] or '',
                    'sizes': row[2] or '',
                    'style_preferences': row[3] or ''
                }), 200
            else:
                return jsonify({
                    'gender': '',
                    'budget_level': '',
                    'sizes': '',
                    'style_preferences': ''
                }), 200
        except Exception:
            logger.exception("Fetching profile failed")
            return jsonify({'error': 'Failed to fetch profile'}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()

    elif request.method == 'POST':
        data = json_object()
        if data is None:
            return jsonify({'error': 'Missing JSON body'}), 400

        fields, error = text_fields(data, PROFILE_FIELDS)
        if error:
            return jsonify({'error': error}), 400

        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_profiles (username, gender, budget_level, sizes, style_preferences)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET gender = EXCLUDED.gender,
                    budget_level = EXCLUDED.budget_level,
                    sizes = EXCLUDED.sizes,
                    style_preferences = EXCLUDED.style_preferences,
                    updated_at = CURRENT_TIMESTAMP;
            """, (username, fields['gender'], fields['budget_level'], fields['sizes'],
                  fields['style_preferences']))
            conn.commit()

            return jsonify({'message': 'Profile saved successfully'}), 200
        except Exception:
            if conn:
                conn.rollback()
            logger.exception("Saving profile failed")
            return jsonify({'error': 'Failed to save profile'}), 500
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
