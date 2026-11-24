import datetime
import hashlib
import logging
from flask import Blueprint, jsonify
from database import get_connection
from request_utils import json_object, parse_id
from security import get_current_user, require_auth
from services.gemini_service import analyze_dress_image_url
import json

logger = logging.getLogger(__name__)

uploads_bp = Blueprint('uploads_bp', __name__)


def _close(conn, cur):
    if cur:
        cur.close()
    if conn:
        conn.close()


@uploads_bp.route('/classify', methods=['POST'])
@require_auth
def classify():
    data = json_object()
    if data is None:
        return jsonify({'error': 'Missing JSON body'}), 400

    image_url = data.get('image_url')
    username = get_current_user().username

    if not isinstance(image_url, str) or not image_url.strip():
        return jsonify({'error': 'image_url missing'}), 400

    # MD5 hash of URL to check for duplicate (since we don't have file bytes)
    image_hash = hashlib.md5(image_url.encode('utf-8')).hexdigest()

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "SELECT image_path, position, style, color FROM uploads WHERE username = %s AND md5_hash = %s",
            (username, image_hash)
        )
        existing = cur.fetchone()
        if existing:
            return jsonify({
                'position': existing[1], 'style': existing[2], 'color': existing[3],
                'message': 'Duplicate image already uploaded.', 'image_url': existing[0]
            })

        # Call Gemini API with the URL
        metadata = analyze_dress_image_url(image_url)

        # Map back to legacy fields
        position = metadata.get("category", "upper")
        style = metadata.get("style", "casual")
        color = metadata.get("primary_color", "black")

        gemini_metadata_json = json.dumps(metadata)

        cur.execute(
            "INSERT INTO uploads (username, image_path, position, style, color, md5_hash, uploaded_at, gemini_metadata) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (username, image_url, position, style, color, image_hash, datetime.datetime.now(), gemini_metadata_json)
        )
        conn.commit()

        return jsonify({'position': position, 'style': style, 'color': color, 'image_url': image_url})
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Classify failed")
        return jsonify({'error': 'Unable to save this image. Please try again.'}), 500
    finally:
        _close(conn, cur)


@uploads_bp.route('/history', methods=['GET'])
@require_auth
def get_history():
    username = get_current_user().username
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, image_path, position, style, color,
                   uploaded_at, favorite
            FROM uploads
            WHERE username = %s
            ORDER BY uploaded_at DESC
            """,
            (username,)
        )

        uploads = cur.fetchall()

        results = [{
            'id': u[0],
            'image_url': u[1],
            'position': u[2],
            'style': u[3],
            'color': u[4],
            'uploaded_at': u[5].isoformat(),
            'favorite': u[6] if u[6] is not None else False
        } for u in uploads]

        return jsonify(results)

    except Exception:
        logger.exception("Loading history failed")
        return jsonify({
            'status': 'error',
            'message': 'Could not load your history. Please try again.'
        }), 500
    finally:
        _close(conn, cur)


@uploads_bp.route('/delete_upload', methods=['POST'])
@require_auth
def delete_upload():
    data = json_object()
    upload_id = parse_id(data.get('upload_id')) if data is not None else None
    if upload_id is None:
        return jsonify({'status': 'error', 'message': 'A valid upload_id is required'}), 400
    username = get_current_user().username

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM uploads WHERE id = %s AND username = %s", (upload_id, username))
        deleted = cur.rowcount
        conn.commit()
        if deleted == 0:
            # Not found and not owned look the same, so ids of other users' uploads are not revealed.
            return jsonify({'status': 'error', 'message': 'Upload not found'}), 404
        return jsonify({'status': 'success'})
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Deleting upload failed")
        return jsonify({'status': 'error', 'message': 'Could not delete the upload. Please try again.'}), 500
    finally:
        _close(conn, cur)


@uploads_bp.route('/get-suggestions', methods=['POST'])
@require_auth
def get_suggestions():
    data = json_object()
    destination = data.get('destination') if data is not None else None
    if not isinstance(destination, str) or not destination:
        return jsonify({'error': 'destination is required'}), 400
    username = get_current_user().username

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT ON (md5_hash) image_path, uploaded_at, style, position, md5_hash
            FROM uploads
            WHERE style = %s AND username = %s
            ORDER BY md5_hash, uploaded_at DESC
        """, (destination, username))

        results = cur.fetchall()
    except Exception:
        logger.exception("Loading suggestions failed")
        return jsonify({'error': 'Could not load suggestions. Please try again.'}), 500
    finally:
        _close(conn, cur)

    suggestions = [{
        'image_url': r[0],
        'uploaded_at': r[1], 'style': r[2], 'position': r[3]
    } for r in results]

    return jsonify({'suggestions': suggestions})


@uploads_bp.route('/toggle_favorite', methods=['POST'])
@require_auth
def toggle_favorite():
    data = json_object()
    upload_id = parse_id(data.get('upload_id')) if data is not None else None
    if upload_id is None:
        return jsonify({'status': 'error', 'message': 'A valid upload_id is required'}), 400
    username = get_current_user().username

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT favorite FROM uploads WHERE id = %s AND username = %s", (upload_id, username))
        result = cur.fetchone()

        if not result:
            return jsonify({'status': 'error', 'message': 'Upload not found'}), 404

        current_favorite = result[0] if result[0] is not None else False
        new_favorite = not current_favorite

        cur.execute("UPDATE uploads SET favorite = %s WHERE id = %s AND username = %s",
                   (new_favorite, upload_id, username))
        conn.commit()

        return jsonify({'status': 'success', 'favorite': new_favorite})
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Toggling favorite failed")
        return jsonify({'status': 'error', 'message': 'Could not update the favorite. Please try again.'}), 500
    finally:
        _close(conn, cur)
