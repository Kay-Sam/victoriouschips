# config.py
import os

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
    SELLER_WHATSAPP = os.getenv("SELLER_WHATSAPP")
    ADMIN_KEY = os.getenv("ADMIN_KEY", "supersecret")
