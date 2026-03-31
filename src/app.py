from flask import Flask

from routes.media import media_bp
from routes.menu import menu_bp
from routes.ai import ai_bp
from routes.operator import operator_bp
app = Flask(__name__)

app.register_blueprint(media_bp)
app.register_blueprint(menu_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(operator_bp)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
