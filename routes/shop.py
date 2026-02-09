# routes/shop.py
from flask import Blueprint, request, jsonify
from models import Order

shop_bp = Blueprint("shop", __name__)

@shop_bp.route("/track-order", methods=["GET"])
def track_order():
    ref = request.args.get("reference")

    order = Order.query.filter_by(reference=ref).first_or_404()

    return jsonify({
        "order_id": order.order_id,
        "status": order.status,
        "total": order.total,
        "items": [
            {"name": i.name, "qty": i.quantity, "price": i.price}
            for i in order.items
        ]
    })
