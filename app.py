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
from datetime import datetime, timezone, timedelta
import resend

app = Flask(__name__)
CORS(app)


# ---------------- KEYS / CONFIG ----------------
PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_PUBLIC = os.getenv("PAYSTACK_PUBLIC_KEY")
SELLER_WHATSAPP = os.getenv("SELLER_WHATSAPP") 
ADMIN_KEY = os.getenv("ADMIN_KEY", "supersecret") 
resend.api_key = os.getenv("RESEND_API_KEY")
#resend.Domains.verify(domain_id="bbd54652-d429-45f4-bdb4-fbbb6dd181f0")

# ---------------- SMTP CONFIG ----------------
# SMTP_SERVER = "smtp.gmail.com"
# SMTP_PORT = 587
# SMTP_FROM = "Victorious Chips <vicaderonkedada@gmail.com>"
# SMTP_USERNAME = os.getenv("SMTP_USERNAME")
# SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# ---------------- HELPER FUNCTION ----------------
def send_email(to_email, subject, html_body):
    try:
        response = resend.Emails.send({
            "from": "Victorious Chips <orders@victoriouschips.com.ng>",
            "to": [to_email],
            "subject": subject,
            "html": html_body,
        })
        print("Resend response:", response)
    except Exception as e:
        print("Resend ERROR:", str(e))
        raise

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

    computed = hmac.new(
        PAYSTACK_SECRET.encode(),
        body,
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


# ---------------- SELLER & BUYER WEBHOOK ----------------
@app.route("/webhook", methods=["POST"])
def webhook():

    # Verify Paystack request is authentic
    if not verify_paystack_signature(request):
        return jsonify({"error": "Invalid signature"}), 400

    event = request.json

    if event.get("event") == "charge.success":

        data = event["data"]
        reference = data.get("reference")

        # Prevent duplicate processing
        if any(order["reference"] == reference for order in orders):
            return jsonify({"status": "already_processed"}), 200


        # ---------------- PAYMENT TIME ----------------
        paid_at_utc = data.get("paid_at")

        if paid_at_utc:

            paid_dt = datetime.strptime(
                paid_at_utc,
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

            paid_dt = paid_dt.replace(
                tzinfo=timezone.utc
            ).astimezone(
                timezone(timedelta(hours=1))
            )

            paid_time = paid_dt.strftime(
                "%d %B %Y, %I:%M %p"
            )

        else:
            paid_time = "N/A"


        # ---------------- METADATA ----------------
        metadata = data.get("metadata", {})
        customer = metadata.get("customer", {})
        cart = metadata.get("cart", [])
        promo = metadata.get("promo")


        # ---------------- CALCULATE EXPECTED TOTAL ----------------
        expected_total = sum(
            int(item.get("price", 0)) *
            int(item.get("quantity", 1))
            for item in cart
        )


        # ---------------- ACTUAL PAID AMOUNT ----------------
        total_paid_naira = data["amount"] / 100

        total_paid = f"₦{total_paid_naira:,.2f}"


        # ---------------- DETECT OVERPAYMENT ----------------
        overpay_amount = (

            total_paid_naira - expected_total

            if total_paid_naira > expected_total

            else 0

        )

        overpay_text = (

            f" (Overpaid ₦{overpay_amount:,.2f})"

            if overpay_amount > 0

            else ""

        )


        # ---------------- FORMAT ITEMS ----------------
        items_list = []
        items_html_list = []

        for item in cart:

            name = item.get("name", "Item")

            price = int(item.get("price", 0))

            quantity = int(item.get("quantity", 1))

            subtotal = price * quantity

            items_list.append(
                f"{name} × {quantity} — ₦{subtotal:,}"
            )

            items_html_list.append(
                f"<li>{name} × {quantity} — ₦{subtotal:,}</li>"
            )

        items_text = "\n".join(items_list)

        items_html = "".join(items_html_list)


        # ---------------- WHATSAPP MESSAGE ----------------
        wa_message = (

            f"🛒 *New Order Received*\n\n"

            f"*Name:* {customer.get('name', 'N/A')}\n"

            f"*Phone:* {customer.get('phone', 'N/A')}\n"

            f"*Email:* {customer.get('email', 'N/A')}\n"

            f"*Address:* {customer.get('address', 'N/A')}\n"

            f"*Promo:* {promo or 'None'}\n\n"

            f"*Items:*\n{items_text}\n\n"

            f"*Expected:* ₦{expected_total:,.2f}\n"

            f"*Paid:* {total_paid}{overpay_text}\n"

            f"*Payment Time:* {paid_time}\n"

            f"*Reference:* {reference}"

        )


        seller_link = (

            f"https://wa.me/{SELLER_WHATSAPP}"

            f"?text={quote_plus(wa_message)}"

        )


        # ---------------- EMAIL BODY ----------------
        html_body = f"""

        <h2>Order Confirmation</h2>

        <p><strong>Name:</strong> {customer.get('name', 'N/A')}</p>

        <p><strong>Phone:</strong> {customer.get('phone', 'N/A')}</p>

        <p><strong>Email:</strong> {customer.get('email', 'N/A')}</p>

        <p><strong>Address:</strong> {customer.get('address', 'N/A')}</p>

        <p><strong>Reference:</strong> {reference}</p>

        <p><strong>Payment Time:</strong> {paid_time}</p>

        <ul>{items_html}</ul>

        <p><strong>Expected Total:</strong> ₦{expected_total:,.2f}</p>

        <p><strong>Total Paid:</strong> {total_paid}{overpay_text}</p>

        """


        # ---------------- SEND EMAILS ----------------
        try:

            # Customer email
            send_email(

                customer.get("email"),

                f"Your Order Confirmation — Ref {reference}",

                html_body

            )


            # Admin email
            send_email(

                "vicaderonkedada@gmail.com",

                f"New Order Received — Ref {reference}",

                html_body

            )


            print("✅ Emails sent successfully")


        except Exception as e:

            print("❌ Email sending failed:", str(e))


        # ---------------- STORE ORDER ----------------
        NIGERIA_TZ = timezone(timedelta(hours=1))

        orders.append({

            "customer": customer,

            "cart": cart,

            "promo": promo,

            "expected_total": expected_total,

            "total_paid": total_paid_naira,

            "overpay": overpay_amount,

            "paid_time": paid_time,

            "reference": reference,

            "wa_link": seller_link,

            "timestamp": datetime.now(

                NIGERIA_TZ

            ).strftime("%d-%m-%Y %H:%M:%S")

        })


        print(

            f"✅ Order processed: {reference} | "

            f"Paid: ₦{total_paid_naira:,.2f} | "

            f"Overpay: ₦{overpay_amount:,.2f} | "

            f"Time: {paid_time}"

        )


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
            dt_utc = datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
            dt_nigeria = dt_utc + timedelta(hours=1)
            formatted_time = dt_nigeria.strftime("%Y-%m-%d %H:%M:%S")

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
# @app.route("/payment-success/<reference>/<phone>")
# def payment_success(reference, phone):
#     message = quote_plus(f"Hello, I just completed payment.\nReference: {reference}\nPhone: {phone}")
#     wa_link = f"https://wa.me/{SELLER_WHATSAPP}?text={message}"
#     return render_template("payment-success.html", wa_link=wa_link , reference=reference)

@app.route("/payment-success/<reference>/<phone>")
def payment_success(reference, phone):
    # Verify transaction with Paystack
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}"}
    res = requests.get(
        f"https://api.paystack.co/transaction/verify/{reference}",
        headers=headers
    )

    if res.status_code != 200:
        abort(404)

    response = res.json()

    if not response.get("status") or response["data"]["status"] != "success":
        abort(404)

    data = response["data"]

    # Pull metadata
    metadata = data.get("metadata", {})
    customer = metadata.get("customer", {})
    cart = metadata.get("cart", [])

    # Normalize cart safely (convert strings to integers)
    items_list = []
    total_amount = 0

    for item in cart:
        name = item.get("name", "Item")
        price = int(item.get("price", 0))
        quantity = int(item.get("quantity", 1))

        subtotal = price * quantity
        total_amount += subtotal

        items_list.append(f"{name} × {quantity} — ₦{subtotal:,}")

    items_text = "\n".join(items_list)

    # Use Paystack amount as final source of truth
    total_paid = f"₦{data['amount'] / 100:,.2f}"

    wa_message = (
        f"🛒 I just made an order!\n\n"
        f"Name: {customer.get('name', 'N/A')}\n"
        f"Phone: {customer.get('phone', 'N/A')}\n"
        f"Reference: {reference}\n\n"
        f"Items:\n{items_text}\n\n"
        f"Total Paid: {total_paid}"
    )

    wa_link = f"https://wa.me/{SELLER_WHATSAPP}?text={quote_plus(wa_message)}"

    return render_template(
        "payment-success.html",
        wa_link=wa_link,
        reference=reference,
        total_paid=total_paid,
        cart=cart,
        customer=customer
    )



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

            # Ensure price and quantity are integers
            cart = metadata.get("cart", [])
            for item in cart:
                item["price"] = int(item.get("price", 0))
                item["quantity"] = int(item.get("quantity", 1))

            # Format timestamp
            paid_at = tx.get("paid_at")
            if paid_at:

                dt_utc = datetime.fromisoformat(paid_at.replace("Z", "+00:00"))
                dt_nigeria = dt_utc + timedelta(hours=1)
                timestamp = dt_nigeria.strftime("%Y-%m-%d %H:%M:%S")

            else:
                timestamp = "N/A"

            order = {
                "reference": reference,
                "customer": metadata.get("customer", {}),
                "cart": cart,
                "promo": metadata.get("promo"),
                "total": tx["amount"] // 100,
                "timestamp": timestamp
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

@app.route("/test-email")
def test_email():
    try:
        send_email("kayodesamuel2588@gmail.com", "Test Email", "<h1>Hello World!</h1>")
        return "Email sent!"
    except Exception as e:
        return f"Error: {e}"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
