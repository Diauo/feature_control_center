from app import db
from app.models.base_models import FeatureExecutionLog, Feature, FeatureExecutionLogDetail
from sqlalchemy import and_, or_, desc
from datetime import datetime
import json

def query_logs(feature_id=None, start_date=None, end_date=None, keyword=None):
    """
    查询日志
    :param feature_id: 功能ID
    :param start_date: 开始日期
    :param end_date: 结束日期
    :param keyword: 关键字
    :return: (bool, str, list) 是否成功，提示信息，日志列表
    """
    try:
        # 构建查询条件
        query = db.session.query(
            FeatureExecutionLog.id,
            FeatureExecutionLog.feature_id,
            FeatureExecutionLog.request_id,
            FeatureExecutionLog.start_time,
            FeatureExecutionLog.end_time,
            FeatureExecutionLog.status,
            FeatureExecutionLog.client_id,
            Feature.name.label('feature_name')
        ).join(Feature, FeatureExecutionLog.feature_id == Feature.id)
        
        # 添加过滤条件
        filters = []
        
        # 按功能ID过滤
        if feature_id:
            filters.append(FeatureExecutionLog.feature_id == feature_id)
            
        # 按日期范围过滤
        if start_date:
            start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
            filters.append(FeatureExecutionLog.start_time >= start_datetime)
            
        if end_date:
            end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
            # 将结束日期设置为当天的23:59:59
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            filters.append(FeatureExecutionLog.start_time <= end_datetime)
            
        # 按关键字过滤
        if keyword:
            filters.append(or_(
                FeatureExecutionLog.request_id.like(f'%{keyword}%'),
                FeatureExecutionLog.status.like(f'%{keyword}%'),
                Feature.name.like(f'%{keyword}%')
            ))
            
        # 应用过滤条件
        if filters:
            query = query.filter(and_(*filters))
            
        # 按开始时间倒序排列
        query = query.order_by(desc(FeatureExecutionLog.start_time))
        
        # 执行查询
        logs = query.all()
        
        # 转换为字典列表
        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'feature_id': log.feature_id,
                'request_id': log.request_id,
                'start_time': log.start_time.strftime('%Y-%m-%d %H:%M:%S') if log.start_time else None,
                'end_time': log.end_time.strftime('%Y-%m-%d %H:%M:%S') if log.end_time else None,
                'status': log.status,
                'client_id': log.client_id,
                'feature_name': log.feature_name
            })
            
        return True, "查询成功", result
    except Exception as e:
        return False, f"查询失败: {str(e)}", []

def get_log_details(log_id):
    """
    获取日志明细内容
    :param log_id: 日志ID
    :return: (bool, str, list) 是否成功，提示信息，日志明细列表
    """
    try:
        # 查询日志记录
        log = FeatureExecutionLog.query.get(log_id)
        if not log:
            return False, "未找到指定的日志记录", None
            
        # 查询关联的日志明细
        log_details = FeatureExecutionLogDetail.query.filter_by(log_id=log_id).order_by(FeatureExecutionLogDetail.timestamp).all()
        
        # 转换为字典列表
        result = []
        for detail in log_details:
            result.append({
                'id': detail.id,
                'log_id': detail.log_id,
                'timestamp': detail.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] if detail.timestamp else None,
                'level': detail.level,
                'message': detail.message,
                'request_id': detail.request_id
            })
            
        return True, "查询成功", result
    except Exception as e:
        return False, f"查询失败: {str(e)}", None