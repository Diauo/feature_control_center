# 用户管理接口设计

## 1. 控制器设计 (UserController)

### 路由前缀
所有用户管理相关接口使用 `/api/users` 前缀。

### 接口列表

#### 1. 获取用户列表
- **URL**: `/api/users`
- **方法**: GET
- **描述**: 获取用户列表（仅超级管理员可用）
- **请求参数**:
  ```query
  page: integer (可选，默认1)
  per_page: integer (可选，默认10)
  role: string (可选，按角色筛选)
  ```
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": {
      "users": [
        {
          "id": "integer",
          "username": "string",
          "email": "string",
          "role": "string",
          "is_active": "boolean",
          "created_date": "datetime"
        }
      ],
      "total": "integer",
      "page": "integer",
      "per_page": "integer"
    }
  }
  ```

#### 2. 获取用户详情
- **URL**: `/api/users/<int:user_id>`
- **方法**: GET
- **描述**: 获取指定用户详情（仅超级管理员可用）
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
      "created_date": "datetime",
      "associated_customers": [
        {
          "id": "integer",
          "name": "string",
          "description": "string"
        }
      ]
    }
  }
  ```

#### 3. 创建用户
- **URL**: `/api/users`
- **方法**: POST
- **描述**: 创建新用户（仅超级管理员可用）
- **请求参数**:
  ```json
  {
    "username": "string",
    "password": "string",
    "email": "string (可选)",
    "role": "string",
    "is_active": "boolean (可选，默认true)",
    "associated_customers": ["integer"] (客户经理关联的客户ID列表)
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

#### 4. 更新用户
- **URL**: `/api/users/<int:user_id>`
- **方法**: PUT
- **描述**: 更新用户信息（仅超级管理员可用）
- **请求参数**:
  ```json
  {
    "username": "string (可选)",
    "email": "string (可选)",
    "role": "string (可选)",
    "is_active": "boolean (可选)",
    "password": "string (可选，修改密码)",
    "associated_customers": ["integer"] (客户经理关联的客户ID列表，可选)
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

#### 5. 删除用户
- **URL**: `/api/users/<int:user_id>`
- **方法**: DELETE
- **描述**: 删除用户（仅超级管理员可用）
- **请求参数**: 无
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": "用户删除成功"
  }
  ```

#### 6. 获取当前用户关联的客户
- **URL**: `/api/users/me/customers`
- **方法**: GET
- **描述**: 获取当前用户关联的客户列表
- **请求参数**: 无
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": [
      {
        "id": "integer",
        "name": "string",
        "description": "string"
      }
    ]
  }
  ```

#### 7. 更新当前用户密码
- **URL**: `/api/users/me/password`
- **方法**: PUT
- **描述**: 更新当前用户密码
- **请求参数**:
  ```json
  {
    "old_password": "string",
    "new_password": "string"
  }
  ```
- **响应**:
  ```json
  {
    "status": true,
    "code": 200,
    "data": "密码更新成功"
  }
  ```

## 2. 服务层设计 (UserService)

### 主要功能

#### 1. 获取用户列表
```python
def get_users(page=1, per_page=10, role=None):
    """
    获取用户列表
    :param page: 页码
    :param per_page: 每页数量
    :param role: 角色筛选
    :return: (bool, str, dict) 是否成功，提示信息，用户列表数据
    """
```

#### 2. 获取用户详情
```python
def get_user_by_id(user_id):
    """
    根据ID获取用户详情
    :param user_id: 用户ID
    :return: User对象或None
    """

def get_user_detail(user_id):
    """
    获取用户详情（包括关联客户）
    :param user_id: 用户ID
    :return: (bool, str, dict) 是否成功，提示信息，用户详情
    """
```

#### 3. 创建用户
```python
def create_user(username, password, email=None, role='operator', is_active=True, associated_customers=None):
    """
    创建新用户
    :param username: 用户名
    :param password: 密码
    :param email: 邮箱
    :param role: 角色
    :param is_active: 是否激活
    :param associated_customers: 关联客户ID列表
    :return: (bool, str, dict) 是否成功，提示信息，用户数据
    """
```

#### 4. 更新用户
```python
def update_user(user_id, username=None, email=None, role=None, is_active=None, password=None, associated_customers=None):
    """
    更新用户信息
    :param user_id: 用户ID
    :param username: 用户名
    :param email: 邮箱
    :param role: 角色
    :param is_active: 是否激活
    :param password: 新密码
    :param associated_customers: 关联客户ID列表
    :return: (bool, str, dict) 是否成功，提示信息，用户数据
    """
```

#### 5. 删除用户
```python
def delete_user(user_id):
    """
    删除用户
    :param user_id: 用户ID
    :return: (bool, str) 是否成功，提示信息
    """
```

#### 6. 获取用户关联的客户
```python
def get_user_associated_customers(user_id):
    """
    获取用户关联的客户
    :param user_id: 用户ID
    :return: 客户列表
    """
```

#### 7. 更新用户关联的客户
```python
def update_user_associated_customers(user_id, customer_ids):
    """
    更新用户关联的客户
    :param user_id: 用户ID
    :param customer_ids: 客户ID列表
    :return: (bool, str) 是否成功，提示信息
    """
```

#### 8. 更新用户密码
```python
def update_user_password(user_id, old_password, new_password):
    """
    更新用户密码
    :param user_id: 用户ID
    :param old_password: 旧密码
    :param new_password: 新密码
    :return: (bool, str) 是否成功，提示信息
    """
```

## 3. 权限控制

### 接口权限要求
1. **超级管理员专用接口**：
   - 获取用户列表
   - 获取用户详情
   - 创建用户
   - 更新用户
   - 删除用户

2. **所有用户可用接口**：
   - 获取当前用户关联的客户
   - 更新当前用户密码

### 权限验证装饰器使用
```python
from app.middlewares import require_role

@user_bp.route('/', methods=['GET'])
@require_role('admin')
def get_users():
    # 实现逻辑
    pass
```

## 4. 数据验证

### 输入验证规则
1. 用户名：长度3-64字符，唯一
2. 密码：长度6-128字符
3. 邮箱：有效邮箱格式（可选）
4. 角色：必须是'admin'、'manager'或'operator'之一
5. 关联客户：必须是有效的客户ID列表

### 验证错误响应
```json
{
  "status": false,
  "code": 400,
  "data": "验证错误信息"
}
```

## 5. 错误处理

### 常见错误响应
1. 用户不存在
2. 用户名已存在
3. 权限不足
4. 数据验证失败
5. 关联客户不存在

## 6. 安全考虑

### 数据保护
1. 密码字段不返回给前端
2. 敏感信息（如密码哈希）不在API响应中暴露
3. 用户列表接口分页处理，避免大量数据传输

### 操作安全
1. 删除用户前确认操作
2. 修改密码需要验证旧密码
3. 超级管理员操作需要额外权限验证

## 7. API调用示例

### 获取用户列表
```bash
curl -X GET "http://localhost:5000/api/users?page=1&per_page=10" \
  -H "Authorization: Bearer <admin_access_token>"
```

### 创建用户
```bash
curl -X POST http://localhost:5000/api/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_access_token>" \
  -d '{
    "username": "newmanager",
    "password": "newpassword",
    "email": "manager@example.com",
    "role": "manager",
    "associated_customers": [1, 2]
  }'
```

### 更新用户
```bash
curl -X PUT http://localhost:5000/api/users/2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <admin_access_token>" \
  -d '{
    "role": "admin",
    "is_active": true
  }'
```

### 删除用户
```bash
curl -X DELETE http://localhost:5000/api/users/2 \
  -H "Authorization: Bearer <admin_access_token>"