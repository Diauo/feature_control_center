# 配置管理控制器设计

## 控制器文件
`app/controllers/config_controller.py`

## 控制器实现

```python
from flask import Blueprint, jsonify, request
from app.services import config_service
from app.models.base_models import Config
from app.middlewares import require_role

config_bp = Blueprint('config', __name__)

def format_response(success, data, code=200):
    """格式化响应数据"""
    return jsonify({
        "status": success,
        "code": code,
        "data": data
    }), code if code != 200 else 200

@config_bp.route('/get_all_config', methods=['GET'])
@require_role('admin')
def get_all_config():
    """获取所有配置"""
    status, msg, data = config_service.get_all_config()
    if not status:
        return msg, 500
    else:
        return jsonify(data), 200

@config_bp.route('/add_config', methods=['POST'])
@require_role('admin')
def add_config():
    """新增配置"""
    request_body = request.get_json()
    if request_body is None:
        return "没有有效的参数", 400
    
    # 创建配置对象
    config = Config(**request_body)
    
    # 调用服务层添加配置
    status, msg, data = config_service.add_config(config)
    if not status:
        return msg, 500
    else:
        return format_response(True, data), 200

@config_bp.route('/update_config/<int:config_id>', methods=['PUT'])
@require_role('admin')
def update_config(config_id):
    """更新配置"""
    request_body = request.get_json()
    if request_body is None:
        return "没有有效的参数", 400
    
    # 调用服务层更新配置
    status, msg, data = config_service.update_config(config_id, request_body)
    if not status:
        return msg, 500
    else:
        return format_response(True, data), 200

@config_bp.route('/delete_config/<int:config_id>', methods=['DELETE'])
@require_role('admin')
def delete_config(config_id):
    """删除配置"""
    # 调用服务层删除配置
    status, msg, data = config_service.delete_config(config_id)
    if not status:
        return msg, 500
    else:
        return format_response(True, msg), 200

@config_bp.route('/reload', methods=['POST'])
@require_role('admin')
def reload_config():
    """重载配置"""
    # 调用服务层重载配置
    status, msg, data = config_service.reload_config()
    if not status:
        return msg, 500
    else:
        return format_response(True, {"message": msg, "config": data}), 200

@config_bp.route('/cleanup', methods=['POST'])
@require_role('admin')
def cleanup_config():
    """清理无效配置"""
    # 调用服务层清理无效配置
    status, msg, data = config_service.cleanup_invalid_config()
    if not status:
        return msg, 500
    else:
        return format_response(True, {"message": msg, "count": data}), 200