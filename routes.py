from flask import request, jsonify, render_template, abort
from config import Config
import uuid, requests, hmac, hashlib, smtplib
from email.message import EmailMessage
from urllib.parse import quote_plus
from datetime import datetime

# In-memory storage for orders
ORDERS = []

# ---------- HELPERS ----------

def apply_promo(cart):
    total = sum(int(i["price"]) * int(i["quantity"]) for i in cart)
    qty = sum(int(i["quantity"]) for i in cart)

    promo = None
    if qty >= 30:
        total = int(total * 0.85)
        promo = "15% Special Offer Sale"

    return total, promo


def send_email(to, subject, body):
    msg = EmailMessage()
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
        server.starttls()
        server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
        server.send_message(msg)


def verify_paystack(req):
    signature = req.headers.get("x-paystack-signature")
    computed = hmac.new(
        Config.PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(signature, computed)


# ---------- ROUTES ----------

def create_payment():
    data = request.json
    cart = data.get("cart", [])
    customer = data.get("customer", {})

    required = ["name", "email", "phone", "address"]
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

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers={"Authorization": f"Bearer {Config.PAYSTACK_SECRET}"}
    )

    if res.status_code != 200:
        return jsonify({"error": "Payment initialization failed"}), 500

    return jsonify({
        "public_key": Config.PAYSTACK_PUBLIC,
        "reference": reference,
        "amount": payload["amount"],
        "email": customer["email"]
    })


def webhook():
    if not verify_paystack(request):
        abort(400)

    event = request.json
    if event["event"] == "charge.success":
        data = event["data"]
        meta = data["metadata"]

        customer = meta["customer"]
        cart = meta["cart"]
        promo = meta.get("promo")
        reference = data["reference"]
        total = data["amount"] // 100

        items_text = "\n".join(
            f"{i['name']} x{i['quantity']} = ₦{int(i['price']) * int(i['quantity'])}"
            for i in cart
        )

        # Email body
        body = f"""
ORDER CONFIRMATION

Reference: {reference}
Name: {customer['name']}
Phone: {customer['phone']}
Email: {customer['email']}
Address: {customer['address']}

Items:
{items_text}

Promo: {promo or 'None'}
Total Paid: ₦{total}
"""

        # Send emails
        send_email(customer["email"], "Your Order Receipt", body)
        send_email("admin@victoriouschips.com.ng", "New Order Received", body)

        # WhatsApp link
        wa_message = quote_plus(f"Hello, I completed payment. Ref: {reference}")
        wa_link = f"https://wa.me/{Config.SELLER_WHATSAPP}?text={wa_message}"

        # Store in memory
        ORDERS.append({
            "reference": reference,
            "customer": customer,
            "cart": cart,
            "total": total,
            "promo": promo,
            "wa_link": wa_link,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })

    return jsonify({"status": "ok"})


def payment_success(reference):
    # Find order
    order = next((o for o in ORDERS if o["reference"] == reference), None)
    if not order:
        abort(404)
    return render_template("payment-success.html", order=order)


def my_orders():
    return render_template("my_orders.html")


def fetch_order(reference):
    order = next((o for o in ORDERS if o["reference"] == reference), None)
    if not order:
        return jsonify({"error": "Order not found"}), 404
    return jsonify(order)


def admin():
    if request.args.get("key") != Config.ADMIN_KEY:
        abort(403)
    return render_template("admin.html", orders=ORDERS)
