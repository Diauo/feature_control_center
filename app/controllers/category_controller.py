from flask import Blueprint, jsonify, request, render_template
from app.services import category_service
from app.models.base_models import Category
from app.util.result import Result
from app.middlewares import require_role, require_customer_access

category_bp = Blueprint('category', __name__)

@category_bp.route('/get_categories', methods=['POST'])
@require_role('admin')
def get_categories():
    """
    管理员用获取所有分类数据接口
    """
    status, msg, data = category_service.get_category_by_customer_id()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@category_bp.route('/get_categories_by_customer_id', methods=['POST'])
@require_role('operator')
@require_customer_access()
def get_categories_by_customer_id():
    """
    操作员用数据获取接口，强制必须携带Query Params customer_id参数
    """
    # 从请求体中获取参数
    request_data = request.get_json()
    customer_id = request_data.get('customer_id') if request_data else None
    
    # 如果请求体中没有customer_id，则从查询参数中获取
    if not customer_id:
        customer_id = request.args.get('customer_id')
    
    if customer_id is None:
        return Result.bad_request("没有有效的参数：客户ID[customer_id]")
    
    status, msg, data = category_service.get_category_by_customer_id(customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@category_bp.route('/add_category', methods=['POST'])
@require_role('admin')
def add_category():
    """
    管理员用新增分类接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    # 检查必要参数
    if 'depth_level' not in request_data:
        return Result.bad_request("没有有效的参数：深度层级[depth_level]")
    if 'parent_id' not in request_data:
        return Result.bad_request("没有有效的参数：父级ID[parent_id]")
    if 'customer_id' not in request_data:
        return Result.bad_request("没有有效的参数：客户[customer_id]")
    
    # 调用服务添加分类
    status, msg, data = category_service.add_category_service(request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "分类添加成功")

@category_bp.route('/del_category', methods=['POST'])
@require_role('admin')
def del_category():
    """
    管理员用删除分类接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    category_id = request_data.get('id')
    if not category_id:
        return Result.bad_request("没有有效的参数：分类ID[id]")
    
    # 调用服务删除分类
    status, msg, data = category_service.del_category(category_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(msg)

@category_bp.route('/update_category', methods=['POST'])
@require_role('admin')
def update_category():
    """
    管理员用更新分类接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    category_id = request_data.get('id')
    if not category_id:
        return Result.bad_request("没有有效的参数：分类ID[id]")
    
    # 调用服务更新分类
    status, msg, data = category_service.update_category_service(category_id, request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "分类更新成功")