from app import db
from app.models.base_models import ScheduledTask, Feature
from sqlalchemy import text
from app.util.serviceUtil import model_to_dict
from datetime import datetime
from apscheduler.triggers.cron import CronTrigger

# 导入调度器实例
try:
    from app.scheduler import task_scheduler
except ImportError:
    task_scheduler = None
def convert_schedule_to_cron(schedule_type, interval_value=None, interval_unit=None, daily_time=None):
    """
    将新的时间定义方式转换为cron表达式
    :param schedule_type: 调度类型 ('interval', 'daily', 'cron')
    :param interval_value: 间隔值
    :param interval_unit: 间隔单位 ('minutes', 'hours', 'days')
    :param daily_time: 每天执行时间 (HH:MM格式)
    :return: cron表达式
    """
    if schedule_type == 'interval':
        if interval_unit == 'minutes':
            return f"*/{interval_value} * * * *"
        elif interval_unit == 'hours':
            return f"0 */{interval_value} * * *"
        elif interval_unit == 'days':
            return f"0 0 */{interval_value} * *"
    elif schedule_type == 'daily':
        hours, minutes = daily_time.split(':')
        return f"{minutes} {hours} * * *"
    elif schedule_type == 'cron':
        # 如果是cron表达式，直接返回
        return None
    return None

def get_all_scheduled_tasks():
    """
    获取所有定时任务
    :return: (bool, str, list) 是否成功，提示信息，定时任务列表
    """
    try:
        tasks = ScheduledTask.query.all()
        # 关联功能名称
        for task in tasks:
            feature = Feature.query.get(task.feature_id)
            if feature:
                task.feature_name = feature.name
        return True, "成功", [task.to_dict() for task in tasks]
    except Exception as e:
        return False, f"查询失败: {str(e)}", []

def get_scheduled_task_by_id(task_id):
    """
    根据ID获取定时任务
    :param task_id: 定时任务ID
    :return: (bool, str, dict) 是否成功，提示信息，定时任务数据
    """
    try:
        task = ScheduledTask.query.get(task_id)
        if not task:
            return False, f"未找到ID为[{task_id}]的定时任务", None
        # 关联功能名称
        feature = Feature.query.get(task.feature_id)
        if feature:
            task.feature_name = feature.name
        return True, "成功", task.to_dict()
    except Exception as e:
        return False, f"查询失败: {str(e)}", None

def add_scheduled_task(task_data):
    """
    添加新定时任务
    :param task_data: 定时任务数据
    :return: (bool, str, dict) 是否成功，提示信息，添加后的数据
    """
    try:
        # 处理新的时间定义方式
        cron_expression = task_data.get('cron_expression')
        if not cron_expression:
            # 如果没有直接提供cron表达式，尝试从新的时间定义方式生成
            schedule_type = task_data.get('schedule_type')
            if schedule_type:
                interval_value = task_data.get('interval_value')
                interval_unit = task_data.get('interval_unit')
                daily_time = task_data.get('daily_time')
                cron_expression = convert_schedule_to_cron(schedule_type, interval_value, interval_unit, daily_time)

        task = ScheduledTask(
            feature_id=task_data.get('feature_id'),
            name=task_data.get('name'),
            description=task_data.get('description'),
            cron_expression=cron_expression,
            is_active=task_data.get('is_active', False)
        )
                # 计算下一次执行时间
        if cron_expression:
            try:
                trigger = CronTrigger.from_crontab(cron_expression)
                next_run_time = trigger.get_next_fire_time(None, datetime.now())
                task.next_run_time = next_run_time
            except Exception as e:
                # 如果计算下一次执行时间失败，记录日志但不中断任务创建
                print(f"计算下一次执行时间失败: {e}")
                
        db.session.add(task)
        db.session.commit()
        
        # 关联功能名称
        feature = Feature.query.get(task.feature_id)
        if feature:
            task.feature_name = feature.name
            
        # 通知调度器添加任务
        if task_scheduler and task.is_active:
            task_scheduler.add_job(task.to_dict())
            
        return True, "添加成功", task.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"添加失败: {str(e)}", None

def update_scheduled_task(task_id, task_data):
    """
    更新指定ID的定时任务
    :param task_id: 定时任务ID
    :param task_data: 定时任务数据
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    try:
        task = ScheduledTask.query.get(task_id)
        if not task:
            return False, f"未找到ID为[{task_id}]的定时任务", None
            
        # 处理新的时间定义方式
        if 'cron_expression' in task_data:
            # 直接更新cron表达式
            task.cron_expression = task_data['cron_expression']
        else:
            # 尝试从新的时间定义方式生成cron表达式
            schedule_type = task_data.get('schedule_type')
            if schedule_type:
                interval_value = task_data.get('interval_value')
                interval_unit = task_data.get('interval_unit')
                daily_time = task_data.get('daily_time')
                cron_expression = convert_schedule_to_cron(schedule_type, interval_value, interval_unit, daily_time)
                if cron_expression:
                    task.cron_expression = cron_expression
            
        # 更新字段
        if 'feature_id' in task_data:
            task.feature_id = task_data['feature_id']
        if 'name' in task_data:
            task.name = task_data['name']
        if 'description' in task_data:
            task.description = task_data['description']
        if 'is_active' in task_data:
            task.is_active = task_data['is_active']
            
        task.updated_date = datetime.now()
        db.session.commit()
        
        # 关联功能名称
        feature = Feature.query.get(task.feature_id)
        if feature:
            task.feature_name = feature.name
            
        # 通知调度器更新任务
        if task_scheduler:
            task_scheduler.update_job(task.to_dict())
            
        return True, "更新成功", task.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"更新失败: {str(e)}", None

def delete_scheduled_task(task_id):
    """
    删除指定ID的定时任务
    :param task_id: 定时任务ID
    :return: (bool, str) 是否成功，提示信息
    """
    try:
        task = ScheduledTask.query.get(task_id)
        if not task:
            return False, f"未找到ID为[{task_id}]的定时任务"
            
        db.session.delete(task)
        db.session.commit()
        
        # 通知调度器移除任务
        if task_scheduler:
            task_scheduler.remove_job(task_id)
            
        return True, "删除成功"
    except Exception as e:
        db.session.rollback()
        return False, f"删除失败: {str(e)}"

def enable_scheduled_task(task_id):
    """
    启用指定ID的定时任务
    :param task_id: 定时任务ID
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    return update_scheduled_task(task_id, {'is_active': True})

def disable_scheduled_task(task_id):
    """
    禁用指定ID的定时任务
    :param task_id: 定时任务ID
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    return update_scheduled_task(task_id, {'is_active': False})

def get_active_scheduled_tasks():
    """
    获取所有启用的定时任务
    :return: (bool, str, list) 是否成功，提示信息，定时任务列表
    """
    try:
        tasks = ScheduledTask.query.filter_by(is_active=True).all()
        # 关联功能名称
        for task in tasks:
            feature = Feature.query.get(task.feature_id)
            if feature:
                task.feature_name = feature.name
        return True, "成功", [task.to_dict() for task in tasks]
    except Exception as e:
        return False, f"查询失败: {str(e)}", []