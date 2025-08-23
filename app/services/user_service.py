from app.models.user_models import User, UserCustomer
from app.models.base_models import Customer
from app import db
from flask_bcrypt import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, create_refresh_token


def get_user_by_id(user_id):
    """
    根据ID获取用户详情
    :param user_id: 用户ID
    :return: User对象或None
    """
    return User.query.get(user_id)


def authenticate_user(username, password):
    """
    验证用户凭据
    :param username: 用户名
    :param password: 密码
    :return: (bool, str, User) 是否成功，提示信息，用户对象
    """
    if not username or not password:
        return False, "用户名和密码不能为空", None
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return False, "用户不存在", None
    
    if not user.check_password(password):
        return False, "密码错误", None
    
    if not user.is_active:
        return False, "用户已被禁用", None
    
    return True, "认证成功", user


def generate_tokens(user):
    """
    为用户生成访问令牌和刷新令牌
    :param user: User对象
    :return: (access_token, refresh_token)
    """
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={'role': user.role}
    )
    refresh_token = create_refresh_token(
        identity=str(user.id),
        additional_claims={'role': user.role}
    )
    return access_token, refresh_token


def register_user(username, password, email=None, role='operator', associated_customers=None):
    """
    注册新用户
    :param username: 用户名
    :param password: 密码
    :param email: 邮箱（可选）
    :param role: 角色（可选，默认为operator）
    :param associated_customers: 关联客户ID列表（可选）
    :return: (bool, str, dict) 是否成功，提示信息，用户数据
    """
    # 验证必填字段
    if not username or not password:
        return False, "用户名和密码不能为空", None
    
    # 检查用户名是否已存在
    if User.query.filter_by(username=username).first():
        return False, "用户名已存在", None
    
    # 创建新用户
    user = User(
        username=username,
        email=email,
        role=role
    )
    
    # 设置密码
    user.set_password(password)
    
    # 保存到数据库
    try:
        db.session.add(user)
        db.session.commit()
        
        # 如果是操作员且有关联客户，创建关联记录
        if role == 'operator' and associated_customers:
            for customer_id in associated_customers:
                user_customer = UserCustomer(
                    user_id=user.id,
                    customer_id=customer_id
                )
                db.session.add(user_customer)
            db.session.commit()
        
        # 返回用户信息（不包含密码哈希）
        user_data = user.to_dict()
        return True, "注册成功", user_data
    except Exception as e:
        db.session.rollback()
        return False, f'注册失败: {str(e)}', None


def is_user_associated_with_customer(user_id, customer_id):
    """
    检查用户是否关联指定客户
    :param user_id: 用户ID
    :param customer_id: 客户ID
    :return: 是否关联
    """
    association = UserCustomer.query.filter_by(user_id=user_id, customer_id=customer_id).first()
    return association is not None


def get_user_associated_customers(user_id):
    """
    获取用户关联的客户
    :param user_id: 用户ID
    :return: 客户列表
    """
    associations = UserCustomer.query.filter_by(user_id=user_id).all()
    customer_ids = [assoc.customer_id for assoc in associations]
    return Customer.query.filter(Customer.id.in_(customer_ids)).all()


def hash_password(password):
    """
    哈希密码
    :param password: 明文密码
    :return: 哈希后的密码
    """
    return generate_password_hash(password).decode('utf-8')


def verify_password(plain_password, hashed_password):
    """
    验证密码
    :param plain_password: 明文密码
    :param hashed_password: 哈希后的密码
    :return: 是否匹配
    """
    return check_password_hash(hashed_password, plain_password)


def get_users(page=1, per_page=10, username=None, role=None):
    """
    获取用户列表
    :param page: 页码
    :param per_page: 每页数量
    :param username: 用户名筛选
    :param role: 角色筛选
    :return: (用户列表, 总数)
    """
    query = User.query
    
    # 添加筛选条件
    if username:
        query = query.filter(User.username.like(f'%{username}%'))
    if role:
        query = query.filter(User.role == role)
    
    # 分页查询
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    users = pagination.items
    total = pagination.total
    
    # 转换为字典列表
    users_data = [user.to_dict() for user in users]
    
    return users_data, total


def update_user(user_id, **kwargs):
    """
    更新用户信息
    :param user_id: 用户ID
    :param kwargs: 要更新的字段
    :return: (bool, str, dict) 是否成功，提示信息，用户数据
    """
    user = User.query.get(user_id)
    if not user:
        return False, "用户不存在", None
    
    # 检查用户名是否已存在（排除当前用户）
    if 'username' in kwargs:
        existing_user = User.query.filter(User.username == kwargs['username'], User.id != user_id).first()
        if existing_user:
            return False, "用户名已存在", None
    
    # 更新用户信息
    for key, value in kwargs.items():
        if key == 'password':
            user.set_password(value)
        elif hasattr(user, key):
            setattr(user, key, value)
    
    # 保存到数据库
    try:
        db.session.commit()
        user_data = user.to_dict()
        return True, "更新成功", user_data
    except Exception as e:
        db.session.rollback()
        return False, f'更新失败: {str(e)}', None


def delete_user(user_id):
    """
    删除用户
    :param user_id: 用户ID
    :return: (bool, str) 是否成功，提示信息
    """
    user = User.query.get(user_id)
    if not user:
        return False, "用户不存在"
    
    # 检查是否是最后一个管理员
    if user.role == 'admin':
        admin_count = User.query.filter(User.role == 'admin').count()
        if admin_count <= 1:
            return False, "不能删除最后一个管理员用户"
    
    try:
        # 删除用户关联的客户关系
        UserCustomer.query.filter_by(user_id=user_id).delete()
        
        # 删除用户
        db.session.delete(user)
        db.session.commit()
        return True, "删除成功"
    except Exception as e:
        db.session.rollback()
        return False, f'删除失败: {str(e)}'