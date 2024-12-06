from flask import Blueprint, jsonify, request, render_template
from app.services import feature_service
feature_bp = Blueprint('feature', __name__)

@feature_bp.route('/get_all_feature', methods=['GET'])
def get_all_feature():
    status, msg, data = feature_service.get_all_feature()
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200

@feature_bp.route('/get_feature_by_customer_id', methods=['GET'])
def get_feature_by_customer_id():
    customer_id = request.args.get('id')
    if not customer_id:
        return "没有有效的参数", 400
    status, msg, data = feature_service.get_feature_by_customer_id(customer_id)
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200