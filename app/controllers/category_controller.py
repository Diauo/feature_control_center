from flask import Blueprint, jsonify, request, render_template
from app.services import category_service

category_bp = Blueprint('category', __name__)

@category_bp.route('/get_category_by_customer_id', methods=['GET'])
def get_category_by_customer_id():
    customer_id = request.args.get('id')
    status, msg, data = category_service.get_category_by_customer_id(customer_id)
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200