from flask import Flask
from flask_cors import CORS
import routes

app = Flask(__name__)
CORS(app)

# Payment routes
app.add_url_rule("/create-payment", view_func=routes.create_payment, methods=["POST"])
app.add_url_rule("/webhook", view_func=routes.webhook, methods=["POST"])
app.add_url_rule("/payment-success/<reference>", view_func=routes.payment_success)
app.add_url_rule("/my-orders", view_func=routes.my_orders)
app.add_url_rule("/fetch-order/<reference>", view_func=routes.fetch_order)

# Admin
app.add_url_rule("/admin", view_func=routes.admin)

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    app.run(debug=True)
