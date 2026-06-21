import sys
import os
import atexit

from flask import Flask, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
# Configure Python Paths
# ─────────────────────────────────────────────────────────────

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# backend/
BACKEND_DIR = os.path.dirname(CURRENT_DIR)

# smart_assisstant/
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# Add paths for imports
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, PROJECT_ROOT)

# ─────────────────────────────────────────────────────────────
# Internal Imports
# ─────────────────────────────────────────────────────────────

from app.config import get_settings
from app.db.mongo import ping_database, close_connection

# ─────────────────────────────────────────────────────────────
# Load Environment Settings
# ─────────────────────────────────────────────────────────────

settings = get_settings()


# ─────────────────────────────────────────────────────────────
# Flask Application Factory
# ─────────────────────────────────────────────────────────────

def create_app() -> Flask:
    """
    Creates and configures the Flask application.
    """

    app = Flask(__name__)

    # ─────────────────────────────────────────────────────────
    # Flask Configuration
    # ─────────────────────────────────────────────────────────

    app.config["SECRET_KEY"] = settings.secret_key
    app.config["DEBUG"] = settings.flask_debug

    # ─────────────────────────────────────────────────────────
    # CORS Configuration
    # ─────────────────────────────────────────────────────────

    CORS(
        app,
        origins=["*"],  # Allow all for development to avoid localhost/127.0.0.1 mismatches
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        supports_credentials=True,
    )

    # ─────────────────────────────────────────────────────────
    # Register Blueprints
    # ─────────────────────────────────────────────────────────

    blueprints = [
        ("auth",      "app.routes.auth",      "auth_bp"),
        ("data",      "app.routes.data",      "data_bp"),
        ("forecast",  "app.routes.forecast",  "forecast_bp"),
        ("anomaly",   "app.routes.anomaly",   "anomaly_bp"),
        ("chat",      "app.routes.chat",      "chat_bp"),
        ("dashboard", "app.routes.dashboard", "dashboard_bp"),
        ("products",  "app.routes.products",  "products_bp"),
        ("orders",    "app.routes.orders",    "orders_bp"),
        ("datasets",  "app.routes.datasets",  "datasets_bp"),
        ("pipeline", "app.routes.pipeline", "pipeline_bp"),
    ]

    for name, module_path, bp_name in blueprints:
        try:
            import importlib
            module = importlib.import_module(module_path)
            bp = getattr(module, bp_name)
            app.register_blueprint(bp)
            print(f"[OK] Blueprint '{name}' registered")
        except Exception as e:
            print(f"[ERROR] Blueprint '{name}' failed to load: {e}")

    # ─────────────────────────────────────────────────────────
    # Root Route
    # ─────────────────────────────────────────────────────────

    @app.route("/", methods=["GET"])
    def root():
        return jsonify({
            "message": "Smart Retail Assistant Backend Running"
        })

    # ─────────────────────────────────────────────────────────
    # Health Check Route
    # ─────────────────────────────────────────────────────────

    @app.route("/health", methods=["GET"])
    def health():

        db_ok = ping_database()

        return jsonify({
            "status": "ok" if db_ok else "degraded",
            "database": "connected" if db_ok else "unreachable",
            "environment": settings.flask_env,
        }), 200 if db_ok else 503

    # ─────────────────────────────────────────────────────────
    # Graceful Shutdown Hook
    # ─────────────────────────────────────────────────────────

    @app.teardown_appcontext
    def shutdown(exception=None):
        """
        Flask teardown hook.
        MongoDB client remains active during app lifecycle.
        """
        pass

    # Close MongoDB connection when process exits
    atexit.register(close_connection)

    return app


# ─────────────────────────────────────────────────────────────
# Run Flask Application
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":

    app = create_app()

    print("\n✅ Smart Retail Assistant backend starting...")
    print(f"🌍 Environment : {settings.flask_env}")
    print("🚀 Server URL  : http://127.0.0.1:5000")
    print("📡 Health URL  : http://127.0.0.1:5000/health\n")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=settings.flask_debug
    )