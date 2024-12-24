from flask import Blueprint, jsonify, request, render_template
from app.services import category_service
from app.models.base_models import Category

category_bp = Blueprint('category', __name__)


@category_bp.route('/get_all_category', methods=['GET'])
def get_all_category():
    status, msg, data = category_service.get_category_by_customer_id()
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200


@category_bp.route('/get_category_by_customer_id', methods=['GET'])
def get_category_by_customer_id():
    customer_id = request.args.get('id')
    if not customer_id:
        return "没有有效的参数：客户ID[customer_id]", 400
    status, msg, data = category_service.get_category_by_customer_id(
        customer_id)
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200


@category_bp.route('/add_category', methods=['POST'])
def add_category():
    request_body = request.get_json()
    if not request_body:
        return "没有有效的参数", 400
    category = Category(**request_body)
    if not category.depth_level:
        return "没有有效的参数：深度层级[depth_level]", 400
    if not category.parent_id:
        return "没有有效的参数：父级ID[parent_id]", 400
    if not category.customer_id:
        return "没有有效的参数：客户[customer_id]", 400
    category.save()
    return "成功", 200
