from flask import Blueprint, jsonify, request, render_template
from app.services import customer_service
from app.util.result import Result
from app.middlewares import require_role, require_customer_access
customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/get_all_customer', methods=['GET'])
@require_role('operator')
def get_all_customer():
    status, msg, data = customer_service.get_all_customer()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@customer_bp.route('/get_customer_by_id', methods=['GET'])
@require_role('operator')
@require_customer_access()
def get_customer_by_id():
    customer_id = request.args.get('id')
    if customer_id is None:
        return Result.bad_request("没有有效的参数")
    status, msg, data = customer_service.get_customer_by_id(customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)