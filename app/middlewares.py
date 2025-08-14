from flask import request, jsonify, current_app, has_request_context
from flask_jwt_extended import verify_jwt_in_request, exceptions as jwt_exceptions, get_jwt_identity, get_jwt
from fnmatch import fnmatch
from app.util import log_utils

def log_request(app):
    @app.before_request
    def just_pass():
        pass

# 配置无需认证的接口白名单
JWT_WHITELIST = [
    ('/api/users/login', 'POST'),
    ('/api/users/register', 'POST'),
    ('/api/users/refresh', 'POST'),
    ('/', 'GET'),
    ('/login', 'GET'),
    ('/favicon.ico', 'GET'),
    ('/static/*', 'GET'),
]

def is_in_whitelist(path, method):
    for rule, m in JWT_WHITELIST:
        # 精确匹配路径和方法
        if path == rule and method == m:
            return True
        # 通配符匹配
        if rule.endswith('/*') and path.startswith(rule[:-1]) and method == m:
            return True
    return False

def jwt_middleware(app):
    @app.before_request
    def check_jwt():
        if is_in_whitelist(request.path, request.method):
            return  # 跳过校验
        try:
            # 验证JWT令牌
            verify_jwt_in_request()
            
            # 获取用户ID和角色
            user_id = get_jwt_identity()
            claims = get_jwt()
            role = claims.get('role')
            
            # 获取用户信息
            from app.services.user_service import get_user_by_id
            user = get_user_by_id(int(user_id))
            if not user or not user.is_active:
                return '用户不存在或已被禁用', 401
            
            # 将用户信息添加到请求上下文
            request.current_user = user
            request.user_role = role
            
        except jwt_exceptions.NoAuthorizationError:
            return '缺少或无效的JWT', 401
        except Exception as e:
            return f'认证失败: {str(e)}', 401

def require_role(required_role):
    """
    角色权限装饰器
    :param required_role: 所需角色
    """
    from functools import wraps
    from flask import request
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
    from app.services.user_service import get_user_by_id
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查是否已经设置了用户信息
            if not hasattr(request, 'current_user') or not hasattr(request, 'user_role'):
                try:
                    # 主动执行JWT验证
                    verify_jwt_in_request()
                    
                    # 获取用户ID和角色
                    user_id = get_jwt_identity()
                    claims = get_jwt()
                    role = claims.get('role')
                    
                    # 获取用户信息
                    user = get_user_by_id(int(user_id))
                    if not user or not user.is_active:
                        return '用户不存在或已被禁用', 401
                    
                    # 将用户信息添加到请求上下文
                    request.current_user = user
                    request.user_role = role
                except Exception as e:
                    return f'认证失败: {str(e)}', 401
            
            # 检查角色权限
            user_role = request.user_role
            # 超级管理员拥有所有权限
            if user_role == 'admin':
                return f(*args, **kwargs)
            
            # 检查其他角色的权限
            if required_role == 'admin' and user_role != 'admin':
                return '权限不足', 403
            if required_role == 'manager' and user_role != 'manager':
                return '权限不足', 403
            if required_role == 'operator' and user_role not in ['operator', 'manager']:
                return '权限不足', 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_customer_access():
    """
    客户访问权限装饰器
    确保客户经理只能访问其关联客户的数据
    """
    from functools import wraps
    from flask import request
    from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
    from app.services.user_service import get_user_by_id, is_user_associated_with_customer
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查是否已经设置了用户信息
            if not hasattr(request, 'current_user') or not hasattr(request, 'user_role'):
                try:
                    # 主动执行JWT验证
                    verify_jwt_in_request()
                    
                    # 获取用户ID和角色
                    user_id = get_jwt_identity()
                    claims = get_jwt()
                    role = claims.get('role')
                    
                    # 获取用户信息
                    user = get_user_by_id(int(user_id))
                    if not user or not user.is_active:
                        return '用户不存在或已被禁用', 401
                    
                    # 将用户信息添加到请求上下文
                    request.current_user = user
                    request.user_role = role
                except Exception as e:
                    return f'认证失败: {str(e)}', 401
            
            # 超级管理员可以访问所有客户数据
            if request.user_role == 'admin':
                return f(*args, **kwargs)
            
            # 客户经理只能访问其关联客户的数据
            if request.user_role == 'manager':
                # 获取请求中的客户ID
                customer_id = request.args.get('customer_id') or (request.json.get('customer_id') if request.json else None)
                if customer_id:
                    # 检查用户是否关联该客户
                    if not is_user_associated_with_customer(request.current_user.id, customer_id):
                        return '权限不足，无法访问该客户数据', 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
        
# 格式化所有返回值
def global_result_format(app):
    @app.after_request
    def result_format(response):
        # 只处理API的返回值
        if request.path.startswith("/api"):
            # 获取响应的原始数据
            response_data = response.get_json()
            
            # 检查是否已经格式化过了（与Result对象格式一致）
            if response_data and isinstance(response_data, dict) and \
               "status" in response_data and "code" in response_data and "data" in response_data:
                # 已经格式化过了，直接返回
                return response
            
            # 对于未格式化的响应，创建标准格式
            status = response.status_code < 400  # 4xx和5xx表示错误
            wrapped_response = {
                "status": status,
                "code" : response.status_code,
                "data": response_data if response_data else response.get_data().decode(),
                "message": "请求成功" if status else "请求失败"
            }
            # 请求成功，只是业务出错。覆写状态码，避免前端直接抛出异常
            response.status_code = 200
            response.set_data(jsonify(wrapped_response).data)
        return response
    
# 异常处理
def app_exception_handler(app):
    @app.errorhandler(Exception)
    def handle_exception(e):
        # 排除常见的HTTP错误状态
        if hasattr(e, 'code') and e.code in {400, 401, 403, 404, 405, 422}:
            return e

        error_message = f"{type(e).__name__}: {str(e)}"
        # 获取请求URL（如果有请求上下文）
        request_info = ""
        if has_request_context():
            request_info = f"接口异常 - URL {request.method}:{request.url}"
            log_utils.logger.error(f"{request_info} \n异常消息： {error_message}", exc_info=True)
        else:
            log_utils.logger.error(f"非接口异常 - {error_message}", exc_info=True)
        return error_message, 500
