import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
from flask import Flask, request, jsonify, render_template, abort
from flask_cors import CORS
import uuid
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
SELLER_WHATSAPP = os.getenv("SELLER_WHATSAPP") 
ADMIN_KEY = os.getenv("ADMIN_KEY", "supersecret") 

# ---------------- SMTP CONFIG ----------------
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_FROM = "Victorious Chips <admin@victoriouschips.com.ng>"
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# ---------------- HELPER FUNCTION ----------------
def send_email(to_email, subject, body):
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_FROM
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        print(f"✅ Email sent successfully to {to_email}")

    except Exception as e:
        print("❌ EMAIL ERROR:", str(e))

# ---------------- ORDERS ----------------
orders = []  # Store latest orders in memory

# ---------------- PROMO LOGIC ----------------
def apply_promo(cart):
    total = sum(float(item["price"]) * int(item["quantity"]) for item in cart)
    total_qty = sum(int(item["quantity"]) for item in cart)
    promo = None

    if total_qty >= 30:
        total *= 0.85
        promo = "15% Special Offer Sale"
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
                {"display_name": "Customer Name", "variable_name": "customer_name", "value": customer["name"]},
                {"display_name": "WhatsApp Number", "variable_name": "whatsapp_number", "value": customer["phone"]},
                {"display_name": "Delivery Address", "variable_name": "delivery_address", "value": customer["address"]}
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
    computed = hmac.new(PAYSTACK_SECRET.encode(), body, hashlib.sha512).hexdigest()
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
        reference = data['reference']
        total_paid = f"₦{data['amount'] / 100}"

        # ---------------- WhatsApp message ----------------
        items_text = "\n".join(f"{item['name']} × {item['quantity']} — ₦{item['price'] * item['quantity']}" for item in cart)
        wa_message = (
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
        seller_link = f"https://wa.me/{SELLER_WHATSAPP}?text={quote_plus(wa_message)}"

        # ---------------- Email ----------------
        items_html = "".join(f"<li>{item['name']} × {item['quantity']} — ₦{item['price'] * item['quantity']}</li>" for item in cart)
        html_body = f"""
        <h2>Order Confirmation</h2>
        <p><strong>Name:</strong> {customer.get('name')}</p>
        <p><strong>Phone:</strong> {customer.get('phone')}</p>
        <p><strong>Email:</strong> {customer.get('email')}</p>
        <p><strong>Address:</strong> {customer.get('address')}</p>
        <p><strong>Promo:</strong> {promo or 'None'}</p>
        <p><strong>Reference:</strong> {reference}</p>
        <ul>{items_html}</ul>
        <p><strong>Total Paid:</strong> {total_paid}</p>
        """
        # Send emails
        send_email(customer.get("email"), f"Your Order Confirmation — Ref {reference}", html_body)
        send_email("vicaderonkedada@gmail.com", f"New Order Received — Ref {reference}", html_body)

        # ---------------- Store order ----------------
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
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    key = request.args.get("key")
    if key != ADMIN_KEY:
        abort(403)

    order = None
    error = None

    if request.method == "POST":
        reference = request.form.get("reference", "").strip()
        if not reference:
            error = "Please enter a payment reference."
            return render_template("admin.html", error=error)

        # Verify transaction with Paystack
        res = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
        )

        if res.status_code != 200:
            error = "Failed to connect to Paystack."
            return render_template("admin.html", error=error)

        response = res.json()
        if not response.get("status"):
            error = response.get("message", "Invalid payment reference.")
            return render_template("admin.html", error=error)

        data = response["data"]
#paid_at = data.get("paid_at", "N/A")
        paid_at = data.get("paid_at")

        if paid_at:
            formatted_time = datetime.fromisoformat(
                paid_at.replace("Z", "+00:00")
            ).strftime("%Y-%m-%d %H:%M:%S")
        else:
            formatted_time = "N/A"
        metadata = data.get("metadata", {})
        customer = metadata.get("customer")
        cart = metadata.get("cart", [])
        promo = metadata.get("promo")

        if not customer or not cart:
            error = "No order metadata found for this payment."
            return render_template("admin.html", error=error)

        for item in cart:
            item["price"] = int(item.get("price", 0))
            item["quantity"] = int(item.get("quantity", 1))

        customer_phone = customer.get("phone", "").replace("+", "").replace(" ", "")
        wa_message = quote_plus(f"Hello {customer.get('name')},\nWe are confirming your order.\n\nReference: {reference}")

        order = {
            "reference": reference,
            "customer": customer,
            "cart": cart,
            "promo": promo,
            "total": data["amount"] // 100,
            "timestamp": formatted_time,   
            "wa_link": f"https://wa.me/{customer_phone}?text={wa_message}"
        }

    return render_template("admin.html", order=order, error=error)

# ---------------- PAYMENT SUCCESS ----------------
@app.route("/payment-success/<reference>/<phone>")
def payment_success(reference, phone):
    message = quote_plus(f"Hello, I just completed payment.\nReference: {reference}\nPhone: {phone}")
    wa_link = f"https://wa.me/{SELLER_WHATSAPP}?text={message}"
    return render_template("payment-success.html", wa_link=wa_link , reference=reference)

@app.route("/my-orders", methods=["GET", "POST"])
def my_orders():
    order = None
    error = None

    if request.method == "POST":
        reference = request.form.get("reference")

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET}"
        }

        res = requests.get(
            f"https://api.paystack.co/transaction/verify/{reference}",
            headers=headers
        )

        data = res.json()

        if not data.get("status"):
            error = "Order not found or invalid reference."
        else:
            tx = data["data"]
            metadata = tx.get("metadata", {})

            order = {
                "reference": reference,
                "customer": metadata.get("customer", {}),
                "cart": metadata.get("cart", []),
                "promo": metadata.get("promo"),
                "total": tx["amount"] // 100,
                "timestamp": tx.get("paid_at")
            }

    return render_template(
    "my_orders.html",
    order=order,
    error=error,
    SELLER_WHATSAPP=SELLER_WHATSAPP
)


@app.route("/health")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(debug=True)
