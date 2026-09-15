from flask import Blueprint, request, jsonify

from app.services.fetch_service import FetchService

integrations_bp = Blueprint("integrations", __name__)
_service = FetchService()


@integrations_bp.route("/api/integrations/fetch")
def fetch():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url is required"}), 400

    body = _service.fetch_remote(url)
    if body is None:
        return jsonify({"error": "fetch failed"}), 502

    return body, 200, {"Content-Type": "text/plain"}
