# app.py
from flask import Flask
from flask_cors import CORS
from config import Config
from models import db

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app)
    db.init_app(app)

    from routes.shop import shop_bp
    from routes.payment import payment_bp
    from routes.admin import admin_bp

    app.register_blueprint(shop_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()

    return app

app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
