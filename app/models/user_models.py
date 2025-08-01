from app import db
from app.models.base_models import Base_model, Customer
from datetime import datetime
from flask_bcrypt import generate_password_hash, check_password_hash


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
    
    def set_password(self, password):
        """设置用户密码"""
        self.password_hash = generate_password_hash(password).decode('utf-8')
    
    def check_password(self, password):
        """检查用户密码"""
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        """将用户对象转换为字典，但不包含密码哈希"""
        data = super().to_dict()
        data.pop('password_hash', None)  # 移除密码哈希字段
        return data


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