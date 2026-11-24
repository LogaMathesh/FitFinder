import json
import logging
from flask import Blueprint, jsonify
from database import get_connection
from request_utils import json_object
from security import require_admin
from services.gemini_service import analyze_dress_image_url

logger = logging.getLogger(__name__)

maintenance_bp = Blueprint('maintenance_bp', __name__)


def _close(conn, cur):
    if cur:
        cur.close()
    if conn:
        conn.close()


@maintenance_bp.route('/check-duplicates', methods=['GET'])
@require_admin
def check_duplicates():
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT image_path, COUNT(*) as count
            FROM uploads
            GROUP BY image_path
            HAVING COUNT(*) > 1
            ORDER BY count DESC
        """)
        duplicates = cur.fetchall()

        if duplicates:
            return jsonify({
                'status': 'found',
                'duplicates': [{'image_path': d[0], 'count': d[1]} for d in duplicates]
            })
        else:
            return jsonify({'status': 'clean', 'message': 'No duplicates found'})
    except Exception:
        logger.exception("Checking duplicates failed")
        return jsonify({'status': 'error', 'message': 'Checking duplicates failed'}), 500
    finally:
        _close(conn, cur)


@maintenance_bp.route('/clean-duplicates', methods=['POST'])
@require_admin
def clean_duplicates():
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            DELETE FROM uploads
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM uploads
                GROUP BY image_path
            )
        """)
        deleted_count = cur.rowcount
        conn.commit()
        return jsonify({
            'status': 'success',
            'message': f'Removed {deleted_count} duplicate entries'
        })
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Cleaning duplicates failed")
        return jsonify({'status': 'error', 'message': 'Cleaning duplicates failed'}), 500
    finally:
        _close(conn, cur)


@maintenance_bp.route('/index-existing-images', methods=['POST'])
@require_admin
def index_existing_images():
    """Admin only: analyze a user's existing images that are missing gemini_metadata.

    The body's username names the TARGET of the admin action. The caller's
    identity and admin rights come from the token (require_admin).
    """
    data = json_object()
    target_username = data.get('username') if data is not None else None
    if not isinstance(target_username, str) or not target_username:
        return jsonify({'error': 'Username required'}), 400

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Only fetch images that haven't been analyzed by Gemini yet
        cur.execute(
            "SELECT id, image_path FROM uploads WHERE username = %s AND gemini_metadata IS NULL",
            (target_username,)
        )
        uploads = cur.fetchall()

        indexed_count = 0
        errors = []

        for upload_id, image_url in uploads:
            try:
                metadata = analyze_dress_image_url(image_url)
                position = metadata.get("category", "upper")
                style = metadata.get("style", "casual")
                color = metadata.get("primary_color", "black")
                gemini_metadata_json = json.dumps(metadata)

                cur.execute(
                    "UPDATE uploads SET gemini_metadata = %s, position = %s, style = %s, color = %s WHERE id = %s",
                    (gemini_metadata_json, position, style, color, upload_id)
                )
                conn.commit()
                indexed_count += 1
            except Exception:
                logger.exception("Indexing upload %s failed", upload_id)
                errors.append(f"Failed to analyze upload {upload_id}")

        return jsonify({
            'message': f'Analyzed {indexed_count} images for Gemini Chatbot',
            'indexed_count': indexed_count,
            'total_pending': len(uploads),
            'errors': errors
        }), 200

    except Exception:
        logger.exception("Indexing existing images failed")
        return jsonify({'error': 'Indexing failed'}), 500
    finally:
        _close(conn, cur)
