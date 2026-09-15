from flask import Blueprint, request, jsonify

from app.services.file_service import FileService

files_bp = Blueprint("files", __name__)
_service = FileService()


@files_bp.route("/api/files/download")
def download():
    filename = request.args.get("filename", "")
    if not filename:
        return jsonify({"error": "filename is required"}), 400

    content = _service.get_file_content(filename)
    if content is None:
        return jsonify({"error": "file not found"}), 404

    return content, 200, {"Content-Type": "application/octet-stream"}
