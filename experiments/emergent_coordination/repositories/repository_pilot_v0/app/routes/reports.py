from flask import Blueprint, request, jsonify

from app.services.report_service import ReportService

reports_bp = Blueprint("reports", __name__)
_service = ReportService()


@reports_bp.route("/api/reports/preview")
def preview():
    title = request.args.get("title", "")
    if not title:
        return jsonify({"error": "title is required"}), 400

    html = _service.render_preview(title)
    return html, 200, {"Content-Type": "text/html"}
