# models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

db = SQLAlchemy()

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(40), unique=True, nullable=False)
    reference = db.Column(db.String(100), unique=True, nullable=False)

    name = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)

    promo = db.Column(db.String(120))
    total = db.Column(db.Integer)
    status = db.Column(db.String(30), default="Paid")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True)

    @staticmethod
    def generate_order_id():
        return f"VC-{uuid.uuid4().hex[:8].upper()}"

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"))
    name = db.Column(db.String(120))
    price = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
