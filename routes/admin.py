from flask import Blueprint, render_template, request, abort
from models import Order
from config import Config

admin_bp = Blueprint("admin", __name__)

@admin_bp.route("/admin")
def admin(): 
    if request.args.get("key") != Config.ADMIN_KEY:
        abort(403)

    # Fetch all orders, newest first
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("admin.html", orders=orders)



@admin_bp.route("/db-test")
def db_test():
    return str(Order.query.count())

