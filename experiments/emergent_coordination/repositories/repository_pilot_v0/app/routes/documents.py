from flask import Blueprint, request, jsonify

from app.services.document_service import DocumentService

documents_bp = Blueprint("documents", __name__)
_service = DocumentService()


@documents_bp.route("/api/documents/download")
def download():
    filename = request.args.get("filename", "")
    if not filename:
        return jsonify({"error": "filename is required"}), 400

    content = _service.get_file_content(filename)
    if content is None:
        return jsonify({"error": "file not found"}), 404

    return content, 200, {"Content-Type": "application/octet-stream"}
