# routes/payment.py
from flask import Blueprint, request, jsonify
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

    payload = {
        "email": customer["email"],
        "amount": data["total"] * 100,
        "reference": reference,
        "metadata": {
            "customer": customer,
            "cart": cart
        }
    }

    res = requests.post(
        "https://api.paystack.co/transaction/initialize",
        json=payload,
        headers={
            "Authorization": f"Bearer {Config.PAYSTACK_SECRET}"
        }
    )

    return jsonify({
        "reference": reference,
        "public_key": Config.PAYSTACK_PUBLIC
    })


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
