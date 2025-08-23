from flask import Blueprint, request, jsonify
import app.services.user_service as user_service
from app import db
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.middlewares import require_role
from app.util.result import Result

user_bp = Blueprint('user_bp', __name__, url_prefix='/api/users')


@user_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return Result.bad_request("用户名和密码不能为空")
    
    # 调用服务层注册用户
    success, message, user_data = user_service.register_user(
        username=data.get('username'),
        password=data.get('password'),
        email=data.get('email'),
        role=data.get('role', 'operator'),
        associated_customers=data.get('associated_customers')
    )
    
    if success:
        return Result.success(user_data)
    else:
        return Result.business_error(message, 400 if "用户名已存在" in message else 500)


@user_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return Result.bad_request("用户名和密码不能为空")
    
    # 验证用户凭据
    success, message, user = user_service.authenticate_user(data['username'], data['password'])
    if not success:
        return Result.unauthorized(message)
    
    # 生成访问令牌和刷新令牌
    access_token, refresh_token = user_service.generate_tokens(user)
    
    # 返回用户信息和令牌
    user_data = user.to_dict()
    return Result.success({
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': user_data
    })


@user_bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """刷新令牌"""
    # 获取当前用户信息
    current_user_id = get_jwt_identity()
    user = user_service.get_user_by_id(int(current_user_id))
    
    if not user:
        return Result.not_found("用户不存在")
    
    # 获取当前令牌的声明
    claims = get_jwt()
    
    # 生成新的访问令牌
    from flask_jwt_extended import create_access_token
    access_token = create_access_token(
        identity=str(current_user_id),
        additional_claims={'role': claims.get('role')}
    )
    
    return Result.success({
        'access_token': access_token
    })


@user_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出"""
    # 在实际应用中，可能需要将令牌加入黑名单
    # 这里我们简化处理，直接返回成功
    return Result.success("登出成功")


@user_bp.route('/me', methods=['GET'])
def get_current_user():
    """获取当前用户信息"""
    current_user_id = get_jwt_identity()
    user = user_service.get_user_by_id(int(current_user_id))
    
    if not user:
        return Result.not_found("用户不存在")
    
    user_data = user.to_dict()
    return Result.success(user_data)


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
    
    return Result.paginated(
        data=users_data,
        total=total,
        page=page,
        per_page=per_page
    )


@user_bp.route('/me/customers', methods=['GET'])
@require_role('operator')
def get_my_customers():
    """获取当前用户关联的客户"""
    # 获取当前用户ID
    current_user_id = get_jwt_identity()
    
    # 调用服务层获取用户关联的客户
    customers = user_service.get_user_associated_customers(current_user_id)
    
    # 转换为客户数据列表
    customers_data = [customer.to_dict() for customer in customers]
    
    return Result.success(customers_data)


@user_bp.route('/<int:user_id>', methods=['GET'])
@require_role('admin')
def get_user(user_id):
    """获取用户详情"""
    user = user_service.get_user_by_id(user_id)
    if not user:
        return Result.not_found("用户不存在")
    
    user_data = user.to_dict()
    return Result.success(user_data)


@user_bp.route('/', methods=['POST'])
@require_role('admin')
def create_user():
    """创建用户"""
    data = request.get_json()
    
    # 验证必填字段
    if not data or not data.get('username') or not data.get('password'):
        return Result.bad_request("用户名和密码不能为空")
    
    # 调用服务层创建用户
    success, message, user_data = user_service.register_user(
        username=data.get('username'),
        password=data.get('password'),
        email=data.get('email'),
        role=data.get('role', 'operator'),
        associated_customers=data.get('associated_customers')
    )
    
    if success:
        return Result.success(user_data, code=201)
    else:
        return Result.business_error(message, 400 if "用户名已存在" in message else 500)


@user_bp.route('/<int:user_id>', methods=['PUT'])
@require_role('admin')
def update_user_endpoint(user_id):
    """更新用户"""
    data = request.get_json()
    
    # 调用服务层更新用户
    success, message, user_data = user_service.update_user(user_id, **data)
    
    if success:
        return Result.success(user_data)
    else:
        return Result.business_error(message, 400 if "用户名已存在" in message else 404)


@user_bp.route('/<int:user_id>', methods=['DELETE'])
@require_role('admin')
def delete_user(user_id):
    """删除用户"""
    # 调用服务层删除用户
    success, message = user_service.delete_user(user_id)
    
    if success:
        return Result.success(message)
    else:
        return Result.business_error(message, 400 if "不能删除最后一个管理员用户" in message else 404)