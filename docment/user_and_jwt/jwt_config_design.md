# JWT配置和初始化设计

## 1. JWT配置

### 配置项说明
在`app/config.py`中添加JWT相关配置：

```python
class Config:
    # 现有配置...
    
    # JWT配置
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'dev-secret-key'
    JWT_ACCESS_TOKEN_EXPIRES = 3600  # 1小时
    JWT_REFRESH_TOKEN_EXPIRES = 86400  # 24小时
```

### 配置说明
- `JWT_SECRET_KEY`: JWT签名密钥，生产环境应从环境变量获取
- `JWT_ACCESS_TOKEN_EXPIRES`: 访问令牌过期时间（秒）
- `JWT_REFRESH_TOKEN_EXPIRES`: 刷新令牌过期时间（秒）

## 2. JWT初始化

### 在应用初始化中添加JWT扩展

在`app/__init__.py`中初始化JWT扩展：

```python
from flask_jwt_extended import JWTManager

# 在create_app函数中添加
def create_app(config_class='app.config.Config'):
    # 现有代码...
    
    # 初始化JWT
    jwt = JWTManager(app)
    
    # 注册JWT错误处理
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return 'Token已过期', 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return '无效的Token', 401

    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return '缺少Token', 401
    
    # 现有代码...
    
    return app
```

## 3. JWT令牌结构

### 访问令牌负载
```json
{
  "identity": "user_id",
  "role": "user_role",
  "fresh": true,
  "type": "access",
  "exp": "expiration_time",
  "iat": "issued_at_time",
  "nbf": "not_before_time",
  "jti": "jwt_id"
}
```

### 刷新令牌负载
```json
{
  "identity": "user_id",
  "role": "user_role",
  "fresh": false,
  "type": "refresh",
  "exp": "expiration_time",
  "iat": "issued_at_time",
  "nbf": "not_before_time",
  "jti": "jwt_id"
}
```

## 4. 安全考虑

### 密钥管理
1. 开发环境：使用默认密钥
2. 生产环境：从环境变量获取密钥
3. 定期轮换密钥

### 令牌过期策略
1. 短期访问令牌（1小时）
2. 较长刷新令牌（24小时）
3. 用户登出时将令牌加入黑名单（需要Redis支持）

## 5. JWT中间件集成

### 在现有中间件基础上扩展
在`app/middlewares.py`中已经实现了基本的JWT验证，后续需要扩展以支持权限验证。

## 6. 环境变量配置示例

### .env文件
```bash
JWT_SECRET_KEY=your-super-secret-jwt-key
JWT_ACCESS_TOKEN_EXPIRES=3600
JWT_REFRESH_TOKEN_EXPIRES=86400