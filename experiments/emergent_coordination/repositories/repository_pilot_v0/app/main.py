from flask import Flask, jsonify

from app.config import APP_NAME, DEBUG, HOST, PORT
from app.routes.documents import documents_bp
from app.routes.files import files_bp
from app.routes.integrations import integrations_bp
from app.routes.reports import reports_bp
from app.routes.webhooks import webhooks_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["APP_NAME"] = APP_NAME
    app.register_blueprint(files_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(integrations_bp)
    app.register_blueprint(webhooks_bp)
    app.register_blueprint(reports_bp)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok", "app": APP_NAME})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=HOST, port=PORT, debug=DEBUG)
