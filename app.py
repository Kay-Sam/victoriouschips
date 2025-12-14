from flask import Flask, request, jsonify
from flask_cors import CORS
import uuid
import os
import requests
import resend

app = Flask(__name__)
CORS(app)

# ---------------- KEYS ----------------
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
SELLER_EMAIL = os.getenv("SELLER_EMAIL")
resend.api_key = os.getenv("RESEND_API_KEY")

# ---------------- PROMO LOGIC ----------------
def apply_promo(cart):
    total = 0
    total_qty = 0

    for item in cart:
        price = float(item["price"])
        qty = int(item["quantity"])
        total += price * qty
        total_qty += qty

    promo = None
    if total_qty >= 30:
        total *= 0.8
        promo = "20% Festive Promo"
    elif total_qty >= 20:
        total *= 0.85
        promo = "15% Festive Promo"

    return int(total), promo

# ---------------- EMAIL ----------------
def send_emails(customer, cart, total, promo, reference):
    items_html = "".join(
        f"<li>{item['name']} x {item['quantity']} — ₦{item['price'] * item['quantity']}</li>"
        for item in cart
    )

    html = f"""
    <h3>Order Receipt</h3>
    <p><strong>Reference:</strong> {reference}</p>
    <p><strong>Name:</strong> {customer['name']}</p>
    <p><strong>Phone:</strong> {customer['phone']}</p>
    <p><strong>Address:</strong> {customer['address']}</p>
    <ul>{items_html}</ul>
    <p><strong>Total Paid:</strong> ₦{total}</p>
    <p>{promo or ''}</p>
    """

    # Buyer email
    resend.Emails.send({
        "from": "Victorious Chips <orders@victoriouschips.com>",
        "to": customer["email"],
        "subject": "Your Order Receipt",
        "html": html
    })

    # Seller email
    resend.Emails.send({
        "from": "Victorious Chips <orders@victoriouschips.com>",
        "to": SELLER_EMAIL,
        "subject": "New Order Received",
        "html": html
    })

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
        "reference": reference
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

    # Send emails immediately after init (acceptable for now)
    send_emails(customer, cart, total, promo, reference)

    return jsonify({
        "public_key": PAYSTACK_PUBLIC,
        "amount": payload["amount"],
        "email": customer["email"],
        "reference": reference,
        "promo": promo
    })

if __name__ == "__main__":
    app.run(debug=True)
