from flask import Blueprint, jsonify, request
from app.services import config_service
from app.models.base_models import Config
from app.middlewares import require_role
from app.util.result import Result
import logging

config_bp = Blueprint('config', __name__)


def validate_config_data(data):
    """验证配置数据"""
    if not data.get('name'):
        return False, "配置名称不能为空"
    
    if 'feature_id' in data and (not isinstance(data['feature_id'], int) or data['feature_id'] < 0):
        return False, "关联功能ID必须是非负整数"
    
    return True, "验证通过"

@config_bp.route('/get_all_config', methods=['GET'])
@require_role('admin')
def get_all_config():
    """获取所有配置"""
    try:
        status, msg, data = config_service.get_all_config()
        if not status:
            logging.error(f"获取配置列表失败: {msg}")
            return Result.error(msg, 500)
        else:
            return Result.success(data)
    except Exception as e:
        logging.error(f"获取配置列表异常: {str(e)}")
        return Result.error(f"获取配置列表失败: {str(e)}", 500)

@config_bp.route('/add_config', methods=['POST'])
@require_role('admin')
def add_config():
    """新增配置"""
    try:
        request_body = request.get_json()
        if request_body is None:
            return Result.bad_request("没有有效的参数")
        
        # 验证数据
        is_valid, message = validate_config_data(request_body)
        if not is_valid:
            return Result.bad_request(message)
        
        # 创建配置对象
        config = Config(**request_body)
        
        # 调用服务层添加配置
        status, msg, data = config_service.add_config(config)
        if not status:
            logging.error(f"添加配置失败: {msg}")
            return Result.error(msg, 500)
        else:
            logging.info(f"成功添加配置: {config.name}")
            return Result.success(data)
    except Exception as e:
        logging.error(f"添加配置异常: {str(e)}")
        return Result.error(f"添加配置失败: {str(e)}", 500)

@config_bp.route('/update_config/<int:config_id>', methods=['PUT'])
@require_role('admin')
def update_config(config_id):
    """更新配置"""
    try:
        request_body = request.get_json()
        if request_body is None:
            return Result.bad_request("没有有效的参数")
        
        # 调用服务层更新配置
        status, msg, data = config_service.update_config(config_id, request_body)
        if not status:
            logging.error(f"更新配置失败: {msg}")
            return Result.error(msg, 500)
        else:
            logging.info(f"成功更新配置: {data.get('name', '未知')}")
            return Result.success(data)
    except Exception as e:
        logging.error(f"更新配置异常: {str(e)}")
        return Result.error(f"更新配置失败: {str(e)}", 500)

@config_bp.route('/delete_config/<int:config_id>', methods=['DELETE'])
@require_role('admin')
def delete_config(config_id):
    """删除配置"""
    try:
        # 调用服务层删除配置
        status, msg, data = config_service.delete_config(config_id)
        if not status:
            logging.error(f"删除配置失败: {msg}")
            return Result.error(msg, 500)
        else:
            logging.info(f"成功删除配置: {config_id}")
            return Result.success(msg)
    except Exception as e:
        logging.error(f"删除配置异常: {str(e)}")
        return Result.error(f"删除配置失败: {str(e)}", 500)

@config_bp.route('/reload', methods=['POST'])
@require_role('admin')
def reload_config():
    """重载配置"""
    try:
        # 调用服务层重载配置
        status, msg, data = config_service.reload_config()
        if not status:
            logging.error(f"重载配置失败: {msg}")
            return Result.error(msg, 500)
        else:
            logging.info("配置重载成功")
            return Result.success({"message": msg, "config": data})
    except Exception as e:
        logging.error(f"重载配置异常: {str(e)}")
        return Result.error(f"重载配置失败: {str(e)}", 500)

@config_bp.route('/cleanup', methods=['POST'])
@require_role('admin')
def cleanup_config():
    """清理无效配置"""
    try:
        # 调用服务层清理无效配置
        status, msg, data = config_service.cleanup_invalid_config()
        if not status:
            logging.error(f"清理无效配置失败: {msg}")
            return Result.error(msg, 500)
        else:
            logging.info(f"清理无效配置完成，共删除{data}个无效配置")
            return Result.success({"message": msg, "count": data})
    except Exception as e:
        logging.error(f"清理无效配置异常: {str(e)}")
        return Result.error(f"清理无效配置失败: {str(e)}", 500)