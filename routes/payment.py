# routes/payment.py
from flask import Blueprint, request, jsonify, render_template
from models import db, Order, OrderItem
from config import Config
import uuid
import requests
import hmac, hashlib

payment_bp = Blueprint("payment", __name__)

# Helper to verify Paystack webhook signature
def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")
    computed = hmac.new(
        Config.PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(signature, computed)

# ---------------- Create Payment ----------------
@payment_bp.route("/create-payment", methods=["POST"])
def create_payment():
    try:
        data = request.json
        cart = data.get("cart", [])
        customer = data.get("customer", {})
    except Exception as e:
        return jsonify({"error": "Invalid JSON payload", "details": str(e)}), 400

    if not cart or not customer:
        return jsonify({"error": "Cart or customer details missing"}), 400

    reference = str(uuid.uuid4())
    total_amount = sum(item.get("price", 0) * item.get("quantity", 1) for item in cart)

    # Save order immediately with status "pending"
    try:
        order = Order(
            order_id=Order.generate_order_id(),
            reference=reference,
            name=customer.get("name"),
            phone=customer.get("phone"),
            email=customer.get("email"),
            address=customer.get("address"),
            total=total_amount,
            status="pending"
        )
        db.session.add(order)
        db.session.flush()
        for item in cart:
            db.session.add(OrderItem(
                order_id=order.id,
                name=item.get("name"),
                price=item.get("price", 0),
                quantity=item.get("quantity", 1)
            ))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Database error", "details": str(e)}), 500

    # Initialize Paystack payment
    payload = {
        "email": customer.get("email"),
        "amount": total_amount * 100,  # in kobo
        "reference": reference,
        "metadata": {
            "customer": customer,
            "cart": cart
        }
    }

    try:
        res = requests.post(
            "https://api.paystack.co/transaction/initialize",
            json=payload,
            headers={"Authorization": f"Bearer {Config.PAYSTACK_SECRET}"}
        )
        paystack_data = res.json()
    except Exception as e:
        return jsonify({"error": "Failed to connect to Paystack", "details": str(e)}), 500

    if not paystack_data.get("status"):
        return jsonify({"error": paystack_data.get("message", "Payment initialization failed")}), 400

    # Return JSON for frontend
    return jsonify({
        "reference": reference,
        "public_key": Config.PAYSTACK_PUBLIC,
        "amount": total_amount * 100,
        "email": customer.get("email")
    })


# ---------------- Webhook ----------------
@payment_bp.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request):
        return "Invalid", 400

    event = request.json
    if event.get("event") == "charge.success":
        data = event.get("data", {})
        ref = data.get("reference")
        order = Order.query.filter_by(reference=ref).first()
        if order:
            order.status = "paid"
            db.session.commit()

    return "OK", 200


# ---------------- Payment Success Page ----------------
@payment_bp.route("/payment-success/<reference>/<phone>")
def payment_success(reference, phone):
    order = Order.query.filter_by(reference=reference, phone=phone).first()
    if not order:
        return "Order not found", 404
    return render_template("payment-success.html", order=order)


def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")
    computed = hmac.new(
        Config.PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(signature, computed)

