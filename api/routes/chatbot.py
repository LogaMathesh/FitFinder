import logging
from flask import Blueprint, jsonify
import rate_limit
from services.gemini_service import suggest_matching_items
from database import get_connection
from request_utils import json_object
from security import get_current_user, require_auth

logger = logging.getLogger(__name__)

# Create blueprint for chatbot routes
chatbot_bp = Blueprint('chatbot', __name__)

@chatbot_bp.route('/chatbot/query', methods=['POST'])
@require_auth
def chatbot_query():
    """Query chatbot for similar images"""
    data = json_object()
    if data is None:
        return jsonify({'error': 'No JSON data provided'}), 400

    username = get_current_user().username
    query_text = data.get('query', '')
    if not isinstance(query_text, str) or not query_text.strip():
        return jsonify({'error': 'Query text required'}), 400
    query_text = query_text.strip()

    limited, usage = rate_limit.consume("chatbot")
    if limited:
        return limited

    try:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT image_path, style, color, position, gemini_metadata FROM uploads WHERE username = %s", (username,))
            rows = cur.fetchall()
            cur.close()
        finally:
            conn.close()

        wardrobe_items = []
        for r in rows:
            url = r[0]
            meta = r[4] if r[4] else {}
            wardrobe_items.append({
                'url': url,
                'style': r[1],
                'color': r[2],
                'position': r[3],
                'metadata': meta
            })

        # If no items, return empty
        if not wardrobe_items:
            return jsonify({
                'results': [],
                'query': query_text,
                'count': 0,
                'usage': usage
            }), 200

        # Ask Gemini to rank items
        matched_urls = suggest_matching_items(query_text, wardrobe_items)

        formatted_results = []
        for url in matched_urls:
            # find style, color for this url
            item = next((x for x in wardrobe_items if x['url'] == url), None)
            if item:
                formatted_results.append({
                    'url': url,
                    'style': item['style'],
                    'color': item['color'],
                    'score': 1.0 # Placeholder since Gemini doesn't return exact distances
                })

        return jsonify({
            'results': formatted_results,
            'query': query_text,
            'count': len(formatted_results),
            'usage': usage
        }), 200

    except Exception:
        logger.exception("Chatbot query failed")
        return jsonify({'error': 'Query failed. Please try again.'}), 500

@chatbot_bp.route('/chatbot/status', methods=['GET'])
def chatbot_status():
    """Check chatbot service status"""
    return jsonify({
        'status': 'active',
        'message': 'Chatbot service is running'
    }), 200
