from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import os
import requests
import hmac
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
CORS(app)

# ---------------- KEYS / CONFIG ----------------
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
SELLER_EMAIL = os.getenv("SELLER_EMAIL")           # Real Gmail for seller
SMTP_EMAIL = os.getenv("SMTP_EMAIL")               # Gmail to send emails from
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")         # Gmail App Password

# ---------------- PROMO LOGIC ----------------
def apply_promo(cart):
    total = sum(float(item["price"]) * int(item["quantity"]) for item in cart)
    total_qty = sum(int(item["quantity"]) for item in cart)
    promo = None

    if total_qty >= 30:
        total *= 0.8
        promo = "20% Festive Promo"
    elif total_qty >= 20:
        total *= 0.85
        promo = "15% Festive Promo"

    return int(total), promo

# ---------------- PAYMENT ----------------
@app.route("/create-payment", methods=["POST"])
def create_payment():
    data = request.json
    cart = data.get("cart", [])
    customer = data.get("customer", {})

    required = ["name", "phone", "address", "email"]
    if not cart or not all(customer.get(k) for k in required):
        return jsonify({"error": "Invalid request"}), 400

    total, promo = apply_promo(cart)
    reference = str(uuid.uuid4())

    payload = {
        "email": customer["email"],
        "amount": total * 100,
        "reference": reference,
        "metadata": {
            "customer": customer,
            "cart": cart,
            "promo": promo
        }
    }

    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers=headers
    )

    if res.status_code != 200:
        return jsonify({"error": "Payment initialization failed"}), 500

    return jsonify({
        "public_key": PAYSTACK_PUBLIC,
        "amount": payload["amount"],
        "email": payload["email"],
        "reference": reference,
        "promo": promo
    })

# ---------------- WEBHOOK SECURITY ----------------
def verify_paystack_signature(req):
    signature = req.headers.get("x-paystack-signature")
    body = req.data
    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        body,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(computed, signature)

# ---------------- EMAIL SENDER ----------------
def send_email(to_emails, subject, html_content):
    msg = MIMEMultipart()
    msg['From'] = f"Victorious Chips <{SMTP_EMAIL}>"
    msg['To'] = ", ".join(to_emails)
    msg['Subject'] = subject
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(SMTP_EMAIL, to_emails, msg.as_string())
        return True
    except Exception as e:
        print("SMTP error:", e)
        return False

# ---------------- SELLER & BUYER WEBHOOK ----------------
@app.route("/webhook", methods=["POST"])
def webhook():
    if not verify_paystack_signature(request):
        return jsonify({"error": "Invalid signature"}), 400

    event = request.json

    if event.get("event") == "charge.success":
        data = event["data"]
        metadata = data.get("metadata", {})
        customer = metadata.get("customer", {})
        cart = metadata.get("cart", [])
        promo = metadata.get("promo")

        items = "".join(
            f"<li>{item['name']} × {item['quantity']} — ₦{item['price'] * item['quantity']}</li>"
            for item in cart
        )

        html = f"""
        <h3>🛒 New Paid Order</h3>
        <p><strong>Name:</strong> {customer.get('name')}</p>
        <p><strong>Phone:</strong> {customer.get('phone')}</p>
        <p><strong>Email:</strong> {customer.get('email')}</p>
        <p><strong>Address:</strong> {customer.get('address')}</p>
        <p><strong>Promo:</strong> {promo or "None"}</p>
        <ul>{items}</ul>
        <p><strong>Total Paid:</strong> ₦{data['amount'] / 100}</p>
        <p><strong>Reference:</strong> {data['reference']}</p>
        """

        # Send email to seller
        send_email([SELLER_EMAIL], "📦 New Order Received", html)
        # Send email to buyer
        send_email([customer.get("email")], "✅ Your Order Receipt", html)

        print("Emails sent to seller and buyer")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True)
