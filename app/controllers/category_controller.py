from flask import Blueprint, jsonify, request, render_template
from app.services import category_service
from app.models.base_models import Category
from app.util.result import Result
from app.middlewares import require_role, require_customer_access

category_bp = Blueprint('category', __name__)


@category_bp.route('/get_all_category', methods=['GET'])
@require_role('operator')
def get_all_category():
    status, msg, data = category_service.get_category_by_customer_id()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)


@category_bp.route('/get_category_by_customer_id', methods=['GET'])
@require_role('operator')
@require_customer_access()
def get_category_by_customer_id():
    customer_id = request.args.get('id')
    if customer_id is None:
        return Result.bad_request("没有有效的参数：客户ID[customer_id]")
    status, msg, data = category_service.get_category_by_customer_id(
        customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)


@category_bp.route('/add_category', methods=['POST'])
@require_role('admin')
def add_category():
    request_body = request.get_json()
    if request_body is None:
        return Result.bad_request("没有有效的参数")
    category = Category(**request_body)
    if category.depth_level is None:
        return Result.bad_request("没有有效的参数：深度层级[depth_level]")
    if category.parent_id is None:
        return Result.bad_request("没有有效的参数：父级ID[parent_id]")
    if category.customer_id is None:
        return Result.bad_request("没有有效的参数：客户[customer_id]")
    result = category.save().to_dict()
    return Result.success(result)


@category_bp.route('/del_category', methods=['POST'])
@require_role('admin')
def del_category():
    request_body = request.get_json()
    if not request_body:
        return Result.bad_request("没有有效的参数")
    category = Category(**request_body)
    status, msg, data = category_service.del_category(category.id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(msg)