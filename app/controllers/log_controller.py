from flask import Blueprint, jsonify, request
from app.services import log_service
from app.util.result import Result
from app.middlewares import require_role

log_bp = Blueprint('log', __name__)

@log_bp.route('/get_logs', methods=['POST'])
@require_role('admin')
def get_logs():
    """
    管理员用获取日志数据接口
    """
    # 获取请求体中的参数
    request_data = request.get_json()
    
    # 调用服务查询日志
    status, msg, data = log_service.query_logs(
        feature_id=request_data.get('feature_id') if request_data else None,
        start_date=request_data.get('start_date') if request_data else None,
        end_date=request_data.get('end_date') if request_data else None,
        keyword=request_data.get('keyword') if request_data else None,
        execution_type=request_data.get('execution_type') if request_data else None
    )
    
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@log_bp.route('/get_logs_by_customer_id', methods=['POST'])
@require_role('operator')
def get_logs_by_customer_id():
    """
    操作员用数据获取接口，强制必须携带Query Params customer_id参数
    """
    # 获取请求体中的参数
    request_data = request.get_json()
    
    # 从请求体中获取customer_id
    customer_id = request_data.get('customer_id') if request_data else None
    
    # 如果请求体中没有customer_id，则从查询参数中获取
    if not customer_id:
        customer_id = request.args.get('customer_id')
    
    if not customer_id:
        return Result.bad_request("缺少参数 customer_id")
    
    # 调用服务查询日志，这里需要根据customer_id过滤日志
    # 由于现有的query_logs方法不支持customer_id过滤，我们需要修改服务方法
    status, msg, data = log_service.query_logs_by_customer_id(
        customer_id=customer_id,
        feature_id=request_data.get('feature_id') if request_data else None,
        start_date=request_data.get('start_date') if request_data else None,
        end_date=request_data.get('end_date') if request_data else None,
        keyword=request_data.get('keyword') if request_data else None,
        execution_type=request_data.get('execution_type') if request_data else None
    )
    
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@log_bp.route('/get_log_details', methods=['POST'])
@require_role('operator')
def get_log_details():
    """
    获取日志明细内容
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("缺少请求参数")
    
    log_id = request_data.get('id')
    if not log_id:
        return Result.bad_request("缺少参数 id")
    
    status, msg, data = log_service.get_log_details(log_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@log_bp.route('/add_log', methods=['POST'])
@require_role('admin')
def add_log():
    """
    管理员用新增日志接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("缺少请求参数")
    
    # 调用服务添加日志
    status, msg, data = log_service.add_log(request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "日志添加成功")

@log_bp.route('/del_log', methods=['POST'])
@require_role('admin')
def del_log():
    """
    管理员用删除日志接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("缺少请求参数")
    
    log_id = request_data.get('id')
    if not log_id:
        return Result.bad_request("缺少参数 id")
    
    # 调用服务删除日志
    status, msg = log_service.del_log(log_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "日志删除成功")

@log_bp.route('/update_log', methods=['POST'])
@require_role('admin')
def update_log():
    """
    管理员用更新日志接口
    """
    request_data = request.get_json()
    if not request_data:
        return Result.bad_request("缺少请求参数")
    
    log_id = request_data.get('id')
    if not log_id:
        return Result.bad_request("缺少参数 id")
    
    # 调用服务更新日志
    status, msg, data = log_service.update_log(log_id, request_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "日志更新成功")