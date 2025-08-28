from flask import Blueprint, jsonify, request, render_template
from app.services import customer_service
from app.util.result import Result
from app.middlewares import require_role, require_customer_access

customer_bp = Blueprint('customer', __name__)

@customer_bp.route('/get_customers', methods=['POST'])
@require_role('operator')  # 需要登录，admin/operator都可访问
def get_customers():
    """
    获取当前用户可见的客户数据接口
    """
    user = getattr(request, "current_user", None)
    role = getattr(request, "user_role", None)
    if not user or not role:
        return Result.error("用户信息获取失败", 401)
    status, msg, data = customer_service.get_all_customer(user.id, role)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)
# ...existing code...

@customer_bp.route('/add_customer', methods=['POST'])
@require_role('admin')
def add_customer():
    """
    管理员用新增客户接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    # 调用服务添加客户
    status, msg, data = customer_service.add_customer(request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "客户添加成功")

@customer_bp.route('/del_customer', methods=['POST'])
@require_role('admin')
def del_customer():
    """
    管理员用删除客户接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    customer_id = request_data.get('id')
    if customer_id is None:
        return Result.bad_request("缺少客户ID参数")
    
    # 调用服务删除客户
    status, msg = customer_service.del_customer(customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "客户删除成功")

@customer_bp.route('/update_customer', methods=['POST'])
@require_role('admin')
def update_customer():
    """
    管理员用更新客户接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    customer_id = request_data.get('id')
    if customer_id is None:
        return Result.bad_request("缺少客户ID参数")
    
    # 调用服务更新客户
    status, msg, data = customer_service.update_customer(customer_id, request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "客户更新成功")