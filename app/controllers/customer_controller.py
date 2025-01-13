from flask import Blueprint, jsonify, request, render_template
from app.services import customer_service
customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/get_all_customer', methods=['GET'])
def get_all_customer():
    status, msg, data = customer_service.get_all_customer()
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200

@customer_bp.route('/get_customer_by_id', methods=['GET'])
def get_customer_by_id():
    customer_id = request.args.get('id')
    if customer_id is None:
        return "没有有效的参数", 400
    status, msg, data = customer_service.get_customer_by_id(customer_id)
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200