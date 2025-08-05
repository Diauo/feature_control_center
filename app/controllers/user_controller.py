from flask import Blueprint, request, jsonify
import app.services.user_service as user_service
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.middlewares import require_role

user_bp = Blueprint('user_bp', __name__, url_prefix='/api/users')


def format_response(success, data, code=200):
    """格式化响应数据"""
    return jsonify({
        "status": success,
        "code": code,
        "data": data
    }), code if code != 200 else 200


@user_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return format_response(False, "用户名和密码不能为空", 400)
    
    # 调用服务层注册用户
    success, message, user_data = user_service.register_user(
        username=data.get('username'),
        password=data.get('password'),
        email=data.get('email'),
        role=data.get('role', 'operator'),
        associated_customers=data.get('associated_customers')
    )
    
    if success:
        return format_response(True, user_data, 200)
    else:
        return format_response(False, message, 400 if "用户名已存在" in message else 500)


@user_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return format_response(False, "用户名和密码不能为空", 400)
    
    # 验证用户凭据
    success, message, user = user_service.authenticate_user(data['username'], data['password'])
    if not success:
        return format_response(False, message, 401)
    
    # 生成访问令牌和刷新令牌
    access_token, refresh_token = user_service.generate_tokens(user)
    
    # 返回用户信息和令牌
    user_data = user.to_dict()
    return format_response(True, {
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user_data
    }, 200)


@user_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """刷新令牌"""
    # 获取当前用户信息
    current_user_id = get_jwt_identity()
    user = user_service.get_user_by_id(int(current_user_id))
    
    if not user:
        return format_response(False, "用户不存在", 404)
    
    # 获取当前令牌的声明
    claims = get_jwt()
    
    # 生成新的访问令牌
    from flask_jwt_extended import create_access_token
    access_token = create_access_token(
        identity=str(current_user_id),
        additional_claims={'role': claims.get('role')}
    )
    
    return format_response(True, {
        'access_token': access_token
    }, 200)


@user_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出"""
    # 在实际应用中，可能需要将令牌加入黑名单
    # 这里我们简化处理，直接返回成功
    return format_response(True, "登出成功", 200)


@user_bp.route('/me', methods=['GET'])
def get_current_user():
    """获取当前用户信息"""
    current_user_id = get_jwt_identity()
    user = user_service.get_user_by_id(int(current_user_id))
    
    if not user:
        return format_response(False, "用户不存在", 404)
    
    user_data = user.to_dict()
    return format_response(True, user_data, 200)


@user_bp.route('/list', methods=['GET'])
@require_role('admin')
def list_users():
    """获取用户列表"""
    # 获取查询参数
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    username = request.args.get('username', type=str)
    role = request.args.get('role', type=str)
    
    # 调用服务层获取用户列表
    users_data, total = user_service.get_users(page=page, per_page=per_page, username=username, role=role)
    
    return format_response(True, {
        'users': users_data,
        'total': total,
        'page': page,
        'per_page': per_page
    }, 200)


@user_bp.route('/<int:user_id>', methods=['GET'])
@require_role('admin')
def get_user(user_id):
    """获取用户详情"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        return format_response(False, "用户不存在", 404)
    
    user_data = user.to_dict()
    return format_response(True, user_data, 200)


@user_bp.route('/', methods=['POST'])
@require_role('admin')
def create_user():
    """创建用户"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return format_response(False, "用户名和密码不能为空", 400)
    
    # 调用服务层创建用户
    success, message, user_data = user_service.register_user(
        username=data.get('username'),
        password=data.get('password'),
        email=data.get('email'),
        role=data.get('role', 'operator'),
        associated_customers=data.get('associated_customers')
    )
    
    if success:
        return format_response(True, user_data, 201)
    else:
        return format_response(False, message, 400 if "用户名已存在" in message else 500)


@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_role('admin')
def update_user_endpoint(user_id):
    """更新用户"""
    data = request.get_json()
    
    # 调用服务层更新用户
    success, message, user_data = user_service.update_user(user_id, **data)
    
    if success:
        return format_response(True, user_data, 200)
    else:
        return format_response(False, message, 400 if "用户名已存在" in message else 404)


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_role('admin')
def delete_user(user_id):
    """删除用户"""
    # 调用服务层删除用户
    success, message = user_service.delete_user(user_id)
    
    if success:
        return format_response(True, message, 200)
    else:
        return format_response(False, message, 400 if "不能删除最后一个管理员用户" in message else 404)