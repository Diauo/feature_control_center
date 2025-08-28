from flask import Blueprint, jsonify, request, render_template
from app.services import feature_service
from app.util.result import Result
from app.middlewares import require_role, require_customer_access

feature_bp = Blueprint('feature', __name__)

@feature_bp.route('/get_features', methods=['POST'])
@require_role('admin')
def get_features():
    """
    管理员用获取所有功能数据接口
    """
    status, msg, data = feature_service.get_all_feature()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@feature_bp.route('/get_features_by_customer_id', methods=['POST'])
@require_role('operator')
@require_customer_access()
def get_features_by_customer_id():
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
        return Result.bad_request("没有有效的参数")
    
    status, msg, data = feature_service.get_feature_by_customer_id(customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@feature_bp.route('/get_feature_by_category_id', methods=['POST'])
@require_role('operator')
def get_feature_by_category_id():
    """
    根据分类ID获取功能列表
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    category_id = request_data.get('category_id')
    customer_id = request_data.get('customer_id')
    
    if category_id is None:
        return Result.bad_request("没有有效的参数")
    
    status, msg, data = feature_service.get_feature_by_category_id(category_id, customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@feature_bp.route('/del_feature', methods=['POST'])
@require_role('admin')
def del_feature():
    """
    管理员用删除功能接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    feature_id = request_data.get('id')
    if feature_id is None:
        return Result.bad_request("缺少功能ID参数")
    
    # 调用服务删除功能
    status, msg = feature_service.delete_feature(feature_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "功能删除成功")

@feature_bp.route('/update_feature', methods=['POST'])
@require_role('admin')
def update_feature():
    """
    管理员用更新功能接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("没有有效的参数")
    
    feature_id = request_data.get('id')
    if feature_id is None:
        return Result.bad_request("缺少功能ID参数")
    
    # 调用服务更新功能
    status, msg, data = feature_service.update_feature_service(feature_id, request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "功能更新成功")

@feature_bp.route('/execute', methods=['POST'])
@require_role('operator')
def execute():
    """
    执行功能
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("缺少请求参数")
    
    feature_id = request_data.get('feature_id')
    if not feature_id:
        return Result.bad_request("缺少参数 feature_id")
    client_id = request_data.get('client_id')
    if not client_id:
        return Result.bad_request("缺少参数 client_id")
    status, msg, _ = feature_service.execute_feature(feature_id, client_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "执行成功")

@feature_bp.route('/register', methods=['POST'])
@require_role('admin')
def register_feature():
    """
    注册新功能
    """
    from app.services import feature_service
    from app.util.result import Result
    
    # 获取上传的文件
    file = request.files.get('file')
    if not file:
        return Result.bad_request("缺少文件参数")
    
    # 获取用户提供的功能信息
    name = request.form.get('name')
    description = request.form.get('description')
    customer_id = request.form.get('customer_id')
    category_id = request.form.get('category_id', 0)
    if not customer_id:
        return Result.bad_request("缺少客户ID参数")
    
    # 调用服务注册功能
    status, msg = feature_service.register_feature(file, name, description, customer_id, category_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "功能注册成功")