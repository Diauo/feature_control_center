from flask import Blueprint, jsonify, request
from app.services import log_service
from app.util.result import Result
from app.middlewares import require_role

log_bp = Blueprint('log', __name__)

@log_bp.route('/query', methods=['GET'])
@require_role('operator')
def query_logs():
    """
    查询日志接口
    支持按功能ID、时间范围、关键字筛选
    """
    # 获取查询参数
    feature_id = request.args.get('feature_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    keyword = request.args.get('keyword')
    execution_type = request.args.get('execution_type')
    
    # 调用服务查询日志
    status, msg, data = log_service.query_logs(
        feature_id=feature_id,
        start_date=start_date,
        end_date=end_date,
        keyword=keyword,
        execution_type=execution_type
    )
    
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@log_bp.route('/get_log_details', methods=['GET'])
@require_role('operator')
def get_log_details():
    """
    获取日志明细内容
    """
    log_id = request.args.get('id', type=int)
    if not log_id:
        return Result.bad_request("缺少参数 id")
    
    status, msg, data = log_service.get_log_details(log_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)