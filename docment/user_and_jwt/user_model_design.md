# 用户和权限数据库模型设计

## 1. 用户表 (User)

### 表结构
```python
class User(Base_model):
    __tablename__ = 'base_user'
    __info__ = ''' 用户表
        存储系统用户信息，包括用户名、密码哈希和角色
    '''
    
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum('admin', 'manager', 'operator'), nullable=False, default='operator')
    email = db.Column(db.String(128), unique=True, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    
    # 关联关系
    customer_associations = db.relationship('UserCustomer', back_populates='user')
```

### 字段说明
- `username`: 用户名，唯一标识用户
- `password_hash`: 密码哈希值，不存储明文密码
- `role`: 用户角色，包括：
  - `admin`: 超级管理员，完全控制系统和权限分配
  - `manager`: 客户经理，能完全控制指定客户的功能管理、运行、日志查看等
  - `operator`: 操作员，只能运行被分配客户所属的功能，查询日志等
- `email`: 用户邮箱（可选）
- `is_active`: 用户是否激活

## 2. 用户-客户关联表 (UserCustomer)

### 表结构
```python
class UserCustomer(Base_model):
    __tablename__ = 'base_user_customer'
    __info__ = ''' 用户-客户关联表
        用于客户经理权限控制，关联用户和客户
    '''
    
    user_id = db.Column(db.Integer, db.ForeignKey('base_user.id'), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey('base_customer.id'), nullable=False)
    
    # 关联关系
    user = db.relationship('User', back_populates='customer_associations')
    customer = db.relationship('Customer')
```

### 字段说明
- `user_id`: 用户ID，外键关联用户表
- `customer_id`: 客户ID，外键关联客户表

## 3. 权限控制逻辑

### 角色权限说明
1. **超级管理员 (admin)**:
   - 完全控制系统所有功能
   - 管理用户和权限分配
   - 查看所有客户的日志和报表

2. **客户经理 (manager)**:
   - 管理指定客户的功能（增删改查）
   - 运行指定客户的功能
   - 查看指定客户的日志和报表
   - 分配定时任务给指定客户的功能

3. **操作员 (operator)**:
   - 运行被分配客户所属的功能
   - 查看被分配客户的日志和报表
   - 无管理权限（不能添加、修改、删除功能）

### 权限验证流程
1. 用户登录后，系统根据其角色确定基本权限
2. 对于客户经理和操作员，系统检查其关联的客户列表
3. 在执行操作时，系统验证用户是否有权操作指定客户的数据

## 4. 数据库关系图

```mermaid
erDiagram
    USER ||--o{ USER_CUSTOMER : has
    USER_CUSTOMER }|--|| CUSTOMER : belongs
    USER {
        int id PK
        string username
        string password_hash
        string role
        string email
        boolean is_active
    }
    USER_CUSTOMER {
        int id PK
        int user_id FK
        int customer_id FK
    }
    CUSTOMER {
        int id PK
        string name
        string description
    }