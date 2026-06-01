import os

from flask import Flask, redirect, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

# Load config FIRST (reads from Secrets Manager or env vars)
from config import SECRET_KEY, SecretsConfig

# Initialize database connection BEFORE importing routes
# (routes import runtime_config which calls db.config_seed at import time)
_database_url = os.environ.get("DATABASE_URL") or SecretsConfig.get("DATABASE_URL", "")
if _database_url:
    os.environ.setdefault("DATABASE_URL", _database_url)

# Seed use cases and roles on first boot (idempotent — skips if data exists)
import db
db.seed_roles_and_admin()
db.migrate_use_cases_from_json()
db.migrate_config_from_json()

# NOW import routes (safe because db is initialized)
from routes.media import media_bp
from routes.menu import menu_bp
from routes.ai import ai_bp
from routes.operator import operator_bp
from routes.admin import admin_bp
from routes.report import report_bp
from routes.users import users_bp
from routes.health import health_bp

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = SECRET_KEY

app.register_blueprint(media_bp)
app.register_blueprint(menu_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(operator_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(report_bp)
app.register_blueprint(users_bp)
app.register_blueprint(health_bp)


@app.route("/")
def index():
    return redirect(url_for("admin.admin"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
