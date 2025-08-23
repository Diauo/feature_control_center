from flask import Blueprint, jsonify, request
from app.services import scheduled_task_service
from app.util.result import Result
from app.middlewares import require_role

scheduled_task_bp = Blueprint('scheduled_task', __name__)

@scheduled_task_bp.route('/get_all', methods=['GET'])
@require_role('operator')
def get_all_scheduled_tasks():
    """
    获取所有定时任务
    """
    status, msg, data = scheduled_task_service.get_all_scheduled_tasks()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@scheduled_task_bp.route('/get/<int:task_id>', methods=['GET'])
@require_role('operator')
def get_scheduled_task(task_id):
    """
    根据ID获取定时任务
    """
    status, msg, data = scheduled_task_service.get_scheduled_task_by_id(task_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@scheduled_task_bp.route('/add', methods=['POST'])
@require_role('admin')
def add_scheduled_task():
    """
    添加新定时任务
    """
    task_data = request.json
    if not task_data:
        return Result.bad_request("缺少请求参数")
        
    # 验证必要参数
    # 检查是否提供了cron_expression或者新的时间定义方式参数
    has_cron_expression = 'cron_expression' in task_data and task_data['cron_expression']
    has_schedule_type = 'schedule_type' in task_data and task_data['schedule_type']
    
    if not has_cron_expression and not has_schedule_type:
        return Result.bad_request("缺少必要参数: cron_expression 或 schedule_type")
    
    # 如果提供了schedule_type，还需要验证相关的参数
    if has_schedule_type:
        schedule_type = task_data['schedule_type']
        if schedule_type == 'interval':
            if 'interval_value' not in task_data or 'interval_unit' not in task_data:
                return Result.bad_request("缺少必要参数: interval_value 或 interval_unit")
        elif schedule_type == 'daily':
            if 'daily_time' not in task_data:
                return Result.bad_request("缺少必要参数: daily_time")
    
    # 验证其他必要参数
    other_required_fields = ['feature_id', 'name']
    for field in other_required_fields:
        if field not in task_data or not task_data[field]:
            return Result.bad_request(f"缺少必要参数: {field}")
    
    status, msg, data = scheduled_task_service.add_scheduled_task(task_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "定时任务添加成功")

@scheduled_task_bp.route('/update/<int:task_id>', methods=['PUT'])
@require_role('admin')
def update_scheduled_task(task_id):
    """
    更新指定ID的定时任务
    """
    task_data = request.json
    if not task_data:
        return Result.bad_request("缺少请求参数")
        
    # 如果提供了schedule_type，还需要验证相关的参数
    if 'schedule_type' in task_data and task_data['schedule_type']:
        schedule_type = task_data['schedule_type']
        if schedule_type == 'interval':
            if 'interval_value' not in task_data or 'interval_unit' not in task_data:
                return Result.bad_request("缺少必要参数: interval_value 或 interval_unit")
        elif schedule_type == 'daily':
            if 'daily_time' not in task_data:
                return Result.bad_request("缺少必要参数: daily_time")
    
    status, msg, data = scheduled_task_service.update_scheduled_task(task_id, task_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "定时任务更新成功")

@scheduled_task_bp.route('/delete/<int:task_id>', methods=['DELETE'])
@require_role('admin')
def delete_scheduled_task(task_id):
    """
    删除指定ID的定时任务
    """
    status, msg = scheduled_task_service.delete_scheduled_task(task_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "定时任务删除成功")

@scheduled_task_bp.route('/enable/<int:task_id>', methods=['POST'])
@require_role('admin')
def enable_scheduled_task(task_id):
    """
    启用指定ID的定时任务
    """
    status, msg, data = scheduled_task_service.enable_scheduled_task(task_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "定时任务已启用")

@scheduled_task_bp.route('/disable/<int:task_id>', methods=['POST'])
@require_role('admin')
def disable_scheduled_task(task_id):
    """
    禁用指定ID的定时任务
    """
    status, msg, data = scheduled_task_service.disable_scheduled_task(task_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data, "定时任务已禁用")