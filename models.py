# Placeholder for future database usage

from datetime import datetime

class Order:
    def __init__(self, reference, customer, cart, total, promo=None):
        self.reference = reference
        self.customer = customer
        self.cart = cart
        self.total = total
        self.promo = promo
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
