# 用户认证接口设计

## 1. 控制器设计 (UserController)

### 路由前缀
所有用户认证相关接口使用 `/api/users` 前缀。

### 接口列表

#### 1. 用户注册
- **URL**: `/api/users/register`
- **方法**: POST
- **描述**: 创建新用户账户
- **请求参数**:
  ```json
  {
    "username": "string",
    "password": "string",
    "email": "string (可选)",
    "role": "string (可选，默认为operator)"
  }
  ```
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": {
      "id": "integer",
      "username": "string",
      "email": "string",
      "role": "string",
      "is_active": "boolean",
      "created_date": "datetime"
    }
  }
  ```

#### 2. 用户登录
- **URL**: `/api/users/login`
- **方法**: POST
- **描述**: 用户登录并获取JWT令牌
- **请求参数**:
  ```json
  {
    "username": "string",
    "password": "string"
  }
  ```
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": {
      "access_token": "string",
      "refresh_token": "string",
      "user": {
        "id": "integer",
        "username": "string",
        "email": "string",
        "role": "string"
      }
    }
  }
  ```

#### 3. 刷新令牌
- **URL**: `/api/users/refresh`
- **方法**: POST
- **描述**: 使用刷新令牌获取新的访问令牌
- **请求参数**:
  ```json
  {
    "refresh_token": "string"
  }
  ```
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": {
      "access_token": "string"
    }
  }
  ```

#### 4. 用户登出
- **URL**: `/api/users/logout`
- **方法**: POST
- **描述**: 用户登出（可选实现令牌黑名单）
- **请求参数**: 无
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": "登出成功"
  }
  ```

#### 5. 获取当前用户信息
- **URL**: `/api/users/me`
- **方法**: GET
- **描述**: 获取当前登录用户的信息
- **请求参数**: 无
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": {
      "id": "integer",
      "username": "string",
      "email": "string",
      "role": "string",
      "is_active": "boolean",
      "created_date": "datetime"
    }
  }
  ```

## 2. 服务层设计 (UserService)

### 主要功能

#### 1. 用户注册
```python
def register_user(username, password, email=None, role='operator'):
    """
    注册新用户
    :param username: 用户名
    :param password: 密码
    :param email: 邮箱（可选）
    :param role: 角色（可选，默认为operator）
    :return: (bool, str, dict) 是否成功，提示信息，用户数据
    """
```

#### 2. 用户认证
```python
def authenticate_user(username, password):
    """
    验证用户凭据
    :param username: 用户名
    :param password: 密码
    :return: (bool, str, User) 是否成功，提示信息，用户对象
    """
```

#### 3. 生成JWT令牌
```python
def generate_tokens(user):
    """
    为用户生成访问令牌和刷新令牌
    :param user: User对象
    :return: (access_token, refresh_token)
    """
```

#### 4. 验证JWT令牌
```python
def verify_token(token):
    """
    验证JWT令牌
    :param token: JWT令牌
    :return: (bool, str, dict) 是否成功，提示信息，令牌数据
    """
```

#### 5. 密码处理
```python
def hash_password(password):
    """
    哈希密码
    :param password: 明文密码
    :return: 哈希后的密码
    """

def verify_password(plain_password, hashed_password):
    """
    验证密码
    :param plain_password: 明文密码
    :param hashed_password: 哈希后的密码
    :return: 是否匹配
    """
```

## 3. 工具函数设计

### JWT工具函数
```python
def create_access_token(identity, role):
    """
    创建访问令牌
    :param identity: 用户标识
    :param role: 用户角色
    :return: 访问令牌
    """

def create_refresh_token(identity, role):
    """
    创建刷新令牌
    :param identity: 用户标识
    :param role: 用户角色
    :return: 刷新令牌
    """
```

### 认证装饰器
```python
def login_required(f):
    """
    登录_required装饰器
    """

def role_required(role):
    """
    角色_required装饰器
    :param role: 所需角色
    """
```

## 4. 错误处理

### 常见错误响应
```json
{
  "status": false,
  "code": 400,
  "data": "错误信息"
}
```

### 错误类型
1. 用户名或密码错误
2. 用户不存在
3. 用户已被禁用
4. 令牌无效或过期
5. 权限不足

## 5. 安全考虑

### 密码安全
1. 使用强哈希算法（如bcrypt）存储密码
2. 设置密码复杂度要求
3. 防止暴力破解（可选实现）

### 令牌安全
1. 使用HTTPS传输令牌
2. 设置合适的令牌过期时间
3. 实现令牌刷新机制
4. 可选实现令牌黑名单机制

## 6. API调用示例

### 注册用户
```bash
curl -X POST http://localhost:5000/api/users/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword",
    "email": "test@example.com"
  }'
```

### 用户登录
```bash
curl -X POST http://localhost:5000/api/users/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "password": "testpassword"
  }'
```

### 获取用户信息
```bash
curl -X GET http://localhost:5000/api/users/me \
  -H "Authorization: Bearer <access_token>"