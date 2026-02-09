# routes/shop.py
from flask import Blueprint, render_template, request, jsonify
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
    
@shop_bp.route("/my-orders")
def my_orders():
    user_phone = request.args.get("phone")  # Or from logged-in user session
    orders = Order.query.filter_by(phone=user_phone).order_by(Order.id.desc()).all()
    return render_template("my_orders.html", orders=orders)
