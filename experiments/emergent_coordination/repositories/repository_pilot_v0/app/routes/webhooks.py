from flask import Blueprint, request, jsonify

from app.services.webhook_service import WebhookService

webhooks_bp = Blueprint("webhooks", __name__)
_service = WebhookService()


@webhooks_bp.route("/api/webhooks/preview")
def preview():
    url = request.args.get("url", "")
    if not url:
        return jsonify({"error": "url is required"}), 400

    body = _service.fetch_remote(url)
    if body is None:
        return jsonify({"error": "fetch failed or url not allowed"}), 502

    return body, 200, {"Content-Type": "text/plain"}
