from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import os
import requests

app = Flask(__name__)
CORS(app)

# ---------------- KEYS ----------------
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
SELLER_EMAIL = os.getenv("SELLER_EMAIL")  # optional for webhook

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
        "amount": total * 100,  # in kobo
        "reference": reference,
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

# ---------------- SELLER WEBHOOK (optional) ----------------
@app.route("/webhook", methods=["POST"])
def webhook():
    event = request.json
    if event.get("event") == "charge.success":
        print("New order received:", event)
        # optionally notify seller here
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(debug=True)
