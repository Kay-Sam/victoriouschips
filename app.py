from flask import Flask, request, jsonify, render_template, abort
from flask_cors import CORS
import uuid
import os
import requests
import hmac
import hashlib
from urllib.parse import quote_plus
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ---------------- KEYS / CONFIG ----------------
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
SELLER_WHATSAPP = os.getenv("SELLER_WHATSAPP")   # Seller WhatsApp number in international format, e.g., +2348012345678
ADMIN_KEY = os.getenv("ADMIN_KEY", "supersecret") # Simple secret key for admin dashboard

# Store latest orders in memory (reset on server restart)
orders = []

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
        "promo": promo,
        "custom_fields": [
            {
                "display_name": "Customer Name",
                "variable_name": "customer_name",
                "value": customer["name"]
            },
            {
                "display_name": "WhatsApp Number",
                "variable_name": "whatsapp_number",
                "value": customer["phone"]
            },
            {
                "display_name": "Delivery Address",
                "variable_name": "delivery_address",
                "value": customer["address"]
            }
        ]
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

        # Prepare order details for WhatsApp
        items_text = "\n".join(f"{item['name']} × {item['quantity']} — ₦{item['price'] * item['quantity']}" for item in cart)
        total_paid = f"₦{data['amount'] / 100}"
        reference = data['reference']

        message = (
            f"🛒 *New Order Received*\n\n"
            f"*Name:* {customer.get('name')}\n"
            f"*Phone:* {customer.get('phone')}\n"
            f"*Email:* {customer.get('email')}\n"
            f"*Address:* {customer.get('address')}\n"
            f"*Promo:* {promo or 'None'}\n"
            f"*Items:*\n{items_text}\n"
            f"*Total Paid:* {total_paid}\n"
            f"*Reference:* {reference}"
        )

        # Encode message for WhatsApp
        wa_message = quote_plus(message)
        seller_link = f"https://wa.me/{SELLER_WHATSAPP}?text={wa_message}"

        # Store order in memory
        orders.append({
            "customer": customer,
            "cart": cart,
            "promo": promo,
            "total": total_paid,
            "reference": reference,
            "wa_link": seller_link,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        print("Order received, seller WhatsApp link:", seller_link)

    return jsonify({"status": "ok"}), 200

# ---------------- ADMIN DASHBOARD ----------------
@app.route("/admin")
def admin_dashboard():
    key = request.args.get("key")
    if key != ADMIN_KEY:
        abort(403)
    return render_template("admin.html", orders=reversed(orders))  # show latest orders first

# ---------------- PAYMENT SUCCESS ----------------
@app.route("/payment-success/<reference>/<phone>")
def payment_success(reference, phone):
    message = quote_plus(
        f"Hello, I just completed payment.\n"
        f"Reference: {reference}\n"
        f"Phone: {phone}"
    )
    wa_link = f"https://wa.me/{SELLER_WHATSAPP}?text={message}"

    return render_template("payment-success.html", wa_link=wa_link)

if __name__ == "__main__":
    app.run(debug=True)


import requests

reference = "d0280326-2711-47c6-aaf5-71a8eef76c7e"

res = requests.get(
    f"https://api.paystack.co/transaction/verify/{reference}",
    headers={
        "Authorization": f"Bearer {PAYSTACK_SECRET}",
        "Content-Type": "application/json"
    }
)

data = res.json()

metadata = data["data"]["metadata"]

customer = metadata["customer"]
cart = metadata["cart"]
promo = metadata.get("promo")
custom_fields = metadata.get("custom_fields")

print(customer)
print(cart)
