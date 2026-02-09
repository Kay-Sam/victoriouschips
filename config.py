import os

class Config:
    # Paystack
    PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")

    # Business
    SELLER_WHATSAPP = os.getenv("SELLER_WHATSAPP")  # e.g., +2348060000000
    ADMIN_KEY = os.getenv("ADMIN_KEY", "supersecret")

    # Gmail SMTP
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    # What users see as sender
    SMTP_FROM = "Victorious Chips <admin@victoriouschips.com.ng>"

    # Real Gmail credentials (hidden via environment variables)
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")  # e.g., vicaderonkedada@gmail.com
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")  # app password
