from flask import Blueprint, request, jsonify
from database import get_connection
from security import get_current_user, require_auth

profile_bp = Blueprint('profile_bp', __name__)

@profile_bp.route('/profile', methods=['GET', 'POST', 'OPTIONS'])
@require_auth
def handle_profile():
    if request.method == 'OPTIONS':
        return jsonify({}), 200

    username = get_current_user().username

    if request.method == 'GET':
        conn = get_connection()
        cur = conn.cursor()
        try:
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
        except Exception as e:
            return jsonify({'error': 'Failed to fetch profile', 'details': str(e)}), 500
        finally:
            cur.close()
            conn.close()

    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Missing JSON body'}), 400

        gender = data.get('gender', '')
        budget_level = data.get('budget_level', '')
        sizes = data.get('sizes', '')
        style_preferences = data.get('style_preferences', '')

        conn = get_connection()
        cur = conn.cursor()
        try:
            cur.execute("""
                INSERT INTO user_profiles (username, gender, budget_level, sizes, style_preferences)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE 
                SET gender = EXCLUDED.gender,
                    budget_level = EXCLUDED.budget_level,
                    sizes = EXCLUDED.sizes,
                    style_preferences = EXCLUDED.style_preferences,
                    updated_at = CURRENT_TIMESTAMP;
            """, (username, gender, budget_level, sizes, style_preferences))
            conn.commit()
            
            return jsonify({'message': 'Profile saved successfully'}), 200
        except Exception as e:
            conn.rollback()
            return jsonify({'error': 'Failed to save profile', 'details': str(e)}), 500
        finally:
            cur.close()
            conn.close()
