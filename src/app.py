from flask import Flask

from routes.media import media_bp
from routes.menu import menu_bp
from routes.ai import ai_bp
from routes.operator import operator_bp
from routes.admin import admin_bp
from config import SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY

app.register_blueprint(media_bp)
app.register_blueprint(menu_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(operator_bp)
app.register_blueprint(admin_bp)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(debug=debug, host="0.0.0.0", port=port)
