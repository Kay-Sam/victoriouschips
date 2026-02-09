# routes/payment.py
from flask import Blueprint, request, jsonify,render_template
from models import db, Order, OrderItem
from config import Config
import uuid
import requests
import hmac, hashlib

payment_bp = Blueprint("payment", __name__)

@payment_bp.route("/create-payment", methods=["POST"])
def create_payment():
    data = request.json
    cart = data["cart"]
    customer = data["customer"]

    reference = str(uuid.uuid4())
    total_amount = sum(item["price"] * item["quantity"] for item in cart)

    # 1️⃣ Save order immediately with status "pending"
    order = Order(
        order_id=Order.generate_order_id(),
        reference=reference,
        name=customer["name"],
        phone=customer["phone"],
        email=customer["email"],
        address=customer["address"],
        total=total_amount,
        status="pending"  # <--- track payment status
    )
    db.session.add(order)
    db.session.flush()
    for item in cart:
        db.session.add(OrderItem(
            order_id=order.id,
            name=item["name"],
            price=item["price"],
            quantity=item["quantity"]
        ))
    db.session.commit()

    # 2️⃣ Initialize payment with Paystack
    payload = {
        "email": customer["email"],
        "amount": total_amount * 100,  # in kobo
        "reference": reference,
        "metadata": {
            "customer": customer,
            "cart": cart
        }
    }

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers={"Authorization": f"Bearer {Config.PAYSTACK_SECRET}"}
    )

    if res.status_code != 200:
        return jsonify({"error": "Payment initialization failed"}), 400

    return jsonify({
        "reference": reference,
        "public_key": Config.PAYSTACK_PUBLIC,
        "amount": total_amount * 100,
        "email": customer["email"]
    })

@payment_bp.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request):
        return "Invalid", 400

    event = request.json
    if event["event"] == "charge.success":
        data = event["data"]
        order = Order.query.filter_by(reference=data["reference"]).first()
        if order:
            order.status = "paid"  # <-- update status
            db.session.commit()

    return "OK", 200


def verify_signature(req):
    signature = req.headers.get("x-paystack-signature")
    computed = hmac.new(
        Config.PAYSTACK_SECRET.encode(),
        req.data,
        hashlib.sha512
    ).hexdigest()
    return hmac.compare_digest(signature, computed)


@payment_bp.route("/webhook", methods=["POST"])
def webhook():
    if not verify_signature(request):
        return "Invalid", 400

    event = request.json

    if event["event"] == "charge.success":
        data = event["data"]
        meta = data["metadata"]
        customer = meta["customer"]
        cart = meta["cart"]

        order = Order(
            order_id=Order.generate_order_id(),
            reference=data["reference"],
            name=customer["name"],
            phone=customer["phone"],
            email=customer["email"],
            address=customer["address"],
            total=data["amount"] // 100
        )

        db.session.add(order)
        db.session.flush()

        for item in cart:
            db.session.add(OrderItem(
                order_id=order.id,
                name=item["name"],
                price=item["price"],
                quantity=item["quantity"]
            ))

        db.session.commit()

    return "OK", 200

@payment_bp.route("/payment-success/<reference>/<phone>")
def payment_success(reference, phone):
    # Find the order by reference
    order = Order.query.filter_by(reference=reference, phone=phone).first()
    if not order:
        return "Order not found", 404

    # You can render a success template and pass order details
    return render_template("payment-success.html", order=order)