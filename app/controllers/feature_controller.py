from flask import Blueprint, jsonify, request, render_template
from app.services import feature_service
from app.util.result import Result
feature_bp = Blueprint('feature', __name__)

@feature_bp.route('/get_all_feature', methods=['GET'])
def get_all_feature():
    status, msg, data = feature_service.get_all_feature()
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@feature_bp.route('/get_feature_by_customer_id', methods=['GET'])
def get_feature_by_customer_id():
    customer_id = request.args.get('id')
    if customer_id is None:
        return Result.bad_request("没有有效的参数")
    status, msg, data = feature_service.get_feature_by_customer_id(customer_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)

@feature_bp.route('/get_feature_by_tags_id', methods=['GET'])
def get_feature_by_category_tags_id():
    tags = request.args.get('tags')
    if tags:
        tags = tags.split(',')
    else:
        return Result.bad_request("没有有效参数标签ID[tags]")
    status, msg, data = feature_service.get_feature_by_tags_id(tags)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(data)
    
@feature_bp.route('/execute', methods=['POST'])
def execute():
    feature_id = request.json.get('feature_id')
    if not feature_id:
        return Result.bad_request("缺少参数 feature_id")
    client_id = request.json.get('client_id')
    if not client_id:
        return Result.bad_request("缺少参数 client_id")
    status, msg, _ = feature_service.execute_feature(feature_id, client_id)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "执行成功")

@feature_bp.route('/register', methods=['POST'])
def register_feature():
    from app.services import feature_service
    from app.util.result import Result
    
    # 获取上传的文件
    file = request.files.get('file')
    if not file:
        return Result.bad_request("缺少文件参数")
    
    # 获取元数据
    meta_data_str = request.form.get('metaData')
    if not meta_data_str:
        return Result.bad_request("缺少元数据参数")
    
    try:
        import json
        meta_data = json.loads(meta_data_str)
    except Exception as e:
        return Result.bad_request("元数据格式不正确")
    
    # 调用服务注册功能
    status, msg = feature_service.register_feature(file, meta_data)
    if not status:
        return Result.error(msg, 500)
    else:
        return Result.success(None, "功能注册成功")