import logging
from flask import Blueprint, request, jsonify
from database import get_connection
from request_utils import json_object, text_fields
from security import get_current_user, require_auth
from psycopg.types.json import Jsonb

logger = logging.getLogger(__name__)

profile_bp = Blueprint('profile_bp', __name__)

# Maximum lengths follow the user_profiles columns (None = TEXT).
PROFILE_FIELDS = {'gender': 50, 'budget_level': 100, 'sizes': None, 'style_preferences': None}
PREFERENCE_OPTIONS = {
    'style_aesthetics': {
        'Casual', 'Streetwear', 'Ethnic', 'Formal', 'Minimal', 'Sporty', 'Vintage', 'Bohemian',
    },
    'occasions': {
        'Everyday', 'Work', 'Social events', 'Travel', 'Parties', 'Weddings',
        'Festive occasions', 'Date nights',
    },
    'preferred_colors': {
        'Neutrals', 'Earth tones', 'Pastels', 'Bright colors', 'Monochrome', 'Jewel tones',
    },
    'fit_priorities': {
        'Comfort', 'Relaxed fit', 'Tailored fit', 'Modest coverage', 'Easy layering',
    },
    'outfit_goals': {
        'Polished', 'Comfortable', 'Expressive', 'Understated', 'Stand out', 'Versatile',
    },
}
PREFERENCE_MAX_SELECTIONS = 5


def _validate_preferences(value):
    if not isinstance(value, dict):
        return None, 'preferences must be an object'
    if set(value) - set(PREFERENCE_OPTIONS):
        return None, 'preferences contains an unsupported field'

    preferences = {}
    for field, options in PREFERENCE_OPTIONS.items():
        selections = value.get(field, [])
        if not isinstance(selections, list):
            return None, f'preferences.{field} must be a list'
        if len(selections) > PREFERENCE_MAX_SELECTIONS:
            return None, f'preferences.{field} must contain at most {PREFERENCE_MAX_SELECTIONS} selections'
        if any(not isinstance(selection, str) or selection not in options for selection in selections):
            return None, f'preferences.{field} contains an unsupported selection'
        if len(set(selections)) != len(selections):
            return None, f'preferences.{field} must not contain duplicates'
        preferences[field] = selections
    return preferences, None


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
                SELECT gender, budget_level, sizes, style_preferences, onboarding_preferences
                FROM user_profiles WHERE username = %s
            """, (username,))
            row = cur.fetchone()

            if row:
                return jsonify({
                    'gender': row[0] or '',
                    'budget_level': row[1] or '',
                    'sizes': row[2] or '',
                    'style_preferences': row[3] or '',
                    'preferences': row[4] or {}
                }), 200
            else:
                return jsonify({
                    'gender': '',
                    'budget_level': '',
                    'sizes': '',
                    'style_preferences': '',
                    'preferences': {}
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

        supplied_fields = {name: data[name] for name in PROFILE_FIELDS if name in data}
        fields, error = text_fields(
            supplied_fields,
            {name: PROFILE_FIELDS[name] for name in supplied_fields},
        )
        if error:
            return jsonify({'error': error}), 400
        fields = {name: fields.get(name) for name in PROFILE_FIELDS}

        preferences = None
        if 'preferences' in data:
            preferences, error = _validate_preferences(data['preferences'])
            if error:
                return jsonify({'error': error}), 400

        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_profiles
                    (username, gender, budget_level, sizes, style_preferences, onboarding_preferences)
                VALUES (%s, %s, %s, %s, %s, COALESCE(%s, '{}'::jsonb))
                ON CONFLICT (username) DO UPDATE
                SET gender = COALESCE(EXCLUDED.gender, user_profiles.gender),
                    budget_level = COALESCE(EXCLUDED.budget_level, user_profiles.budget_level),
                    sizes = COALESCE(EXCLUDED.sizes, user_profiles.sizes),
                    style_preferences = COALESCE(EXCLUDED.style_preferences, user_profiles.style_preferences),
                    onboarding_preferences = COALESCE(
                        EXCLUDED.onboarding_preferences, user_profiles.onboarding_preferences
                    ),
                    updated_at = CURRENT_TIMESTAMP;
            """, (
                username, fields['gender'], fields['budget_level'], fields['sizes'],
                fields['style_preferences'], Jsonb(preferences) if preferences is not None else None,
            ))
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
