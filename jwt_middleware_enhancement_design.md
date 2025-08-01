# JWT中间件增强设计（权限验证）

## 1. 现有中间件分析

当前系统在`app/middlewares.py`中已经实现了基本的JWT验证，但缺少权限控制功能。现有功能包括：
- JWT令牌验证
- 白名单机制（无需认证的接口）
- 全局结果格式化
- 异常处理

## 2. 增强需求

### 权限控制需求
1. 基于角色的访问控制（RBAC）
2. 客户经理只能访问其关联客户的数据
3. 操作员只能执行被分配客户所属的功能

### 扩展功能
1. 在请求上下文中添加用户信息
2. 实现细粒度权限验证
3. 支持客户关联验证

## 3. 设计方案

### 3.1 增强JWT中间件

修改`app/middlewares.py`中的`jwt_middleware`函数：

```python
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity, get_jwt
from app.services.user_service import get_user_by_id

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
            user = get_user_by_id(user_id)
            if not user or not user.is_active:
                return '用户不存在或已被禁用', 401
            
            # 将用户信息添加到请求上下文
            request.current_user = user
            request.user_role = role
            
        except jwt_exceptions.NoAuthorizationError:
            return '缺少或无效的JWT', 401
        except Exception as e:
            return f'认证失败: {str(e)}', 401
```

### 3.2 权限验证装饰器

创建权限验证装饰器，用于保护特定路由：

```python
from functools import wraps
from flask import request

def require_role(required_role):
    """
    角色_required装饰器
    :param required_role: 所需角色
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查用户是否已认证
            if not hasattr(request, 'current_user') or not hasattr(request, 'user_role'):
                return '未认证', 401
            
            # 检查角色权限
            user_role = request.user_role
            if user_role != 'admin':  # 超级管理员拥有所有权限
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
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 检查用户是否已认证
            if not hasattr(request, 'current_user') or not hasattr(request, 'user_role'):
                return '未认证', 401
            
            # 超级管理员可以访问所有客户数据
            if request.user_role == 'admin':
                return f(*args, **kwargs)
            
            # 客户经理只能访问其关联客户的数据
            if request.user_role == 'manager':
                # 获取请求中的客户ID
                customer_id = request.args.get('customer_id') or request.json.get('customer_id')
                if customer_id:
                    # 检查用户是否关联该客户
                    if not is_user_associated_with_customer(request.current_user.id, customer_id):
                        return '权限不足，无法访问该客户数据', 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### 3.3 客户关联验证服务

在`app/services/user_service.py`中添加客户关联验证函数：

```python
def is_user_associated_with_customer(user_id, customer_id):
    """
    检查用户是否关联指定客户
    :param user_id: 用户ID
    :param customer_id: 客户ID
    :return: 是否关联
    """
    from app.models.user_models import UserCustomer
    association = UserCustomer.query.filter_by(user_id=user_id, customer_id=customer_id).first()
    return association is not None
```

## 4. 权限控制流程

### 4.1 基本权限控制
1. 用户登录后，JWT令牌中包含用户角色信息
2. 中间件验证令牌并解析角色信息
3. 路由装饰器检查用户角色是否满足要求

### 4.2 客户关联权限控制
1. 客户经理访问客户相关数据时，系统检查其是否关联该客户
2. 通过`require_customer_access`装饰器实现
3. 超级管理员可以访问所有客户数据

## 5. 使用示例

### 5.1 控制器中使用角色权限装饰器
```python
from app.middlewares import require_role, require_customer_access

@feature_bp.route('/get_all_feature', methods=['GET'])
@require_role('operator')  # 操作员及以上角色可以访问
def get_all_feature():
    # 实现逻辑
    pass

@feature_bp.route('/add_feature', methods=['POST'])
@require_role('manager')  # 只有客户经理和超级管理员可以添加功能
@require_customer_access()  # 客户经理只能添加关联客户的功能
def add_feature():
    # 实现逻辑
    pass
```

### 5.2 在服务层使用权限检查
```python
from flask import request

def update_feature(feature_id, name=None, description=None, customer_id=None):
    # 检查权限
    if request.user_role not in ['admin', 'manager']:
        return False, "权限不足", None
    
    # 客户经理只能更新关联客户的功能
    if request.user_role == 'manager':
        if not is_user_associated_with_customer(request.current_user.id, customer_id):
            return False, "权限不足，无法更新该客户的功能", None
    
    # 实现更新逻辑
    # ...
```

## 6. 错误处理

### 权限相关错误响应
```json
{
  "status": false,
  "code": 403,
  "data": "权限不足"
}
```

### 错误类型
1. 未认证访问受保护资源
2. 角色权限不足
3. 客户关联权限不足

## 7. 安全考虑

### 权限验证
1. 在每个需要权限控制的接口上使用适当的装饰器
2. 在服务层进行二次权限检查
3. 防止越权访问客户数据

### 数据隔离
1. 客户经理只能看到和操作其关联客户的数据
2. 操作员只能执行被分配客户所属的功能
3. 超级管理员可以访问所有数据

## 8. 性能优化

### 缓存用户关联信息
1. 在用户登录时缓存其关联的客户列表
2. 减少数据库查询次数
3. 提高权限验证效率