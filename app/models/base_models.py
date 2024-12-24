from app import db
from datetime import datetime


class Base_model(db.Model):
    __tablename__ = "base"
    __abstract__ = True  # 标记为抽象类，不会映射到具体的表

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_date = db.Column(db.DateTime, default=datetime.now)
    updated_date = db.Column(
        db.DateTime, default=datetime.now, onupdate=datetime.now)

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        name = getattr(self, 'name', '无名model')
        return f"<{name}>"


class Feature(Base_model):
    __tablename__ = 'base_feature'
    __info__ = ''' 功能
        一段轻量化可移植的代码逻辑
    '''
    name = db.Column(db.String(64), unique=False, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)
    customer_id = db.Column(db.Integer, unique=False, nullable=False)
    tags = ""
    customer_name = ""


class Category(Base_model):
    __tablename__ = 'base_category'
    __info__ = ''' 分类
        分类决定功能页面展示的主要分类，下面可以设置一个或多个标签用于过滤功能；
        分类不与功能直接关联，而是通过标签间接关联
        分类存在上下级关系，可以定义复杂的嵌套。
    '''
    name = db.Column(db.String(64), unique=False, nullable=False)
    parent_id = db.Column(db.Integer, unique=False, nullable=True)
    customer_id = db.Column(db.Integer, unique=False, nullable=True)
    description = db.Column(db.String(256), unique=False, nullable=True)
    order_id = db.Column(db.Integer, unique=False,
                         nullable=True, autoincrement=True)
    # 在树状结构中的深度级别，子类继承父类的层级
    depth_level = db.Column(db.Integer, unique=False,
                            nullable=False, default=0)
    tags = ""

class Tag(Base_model):
    __tablename__ = 'base_tag'
    __info__ = ''' 标签
        标签用于标识功能，来实现过滤和搜索等功能的实现
    '''
    name = db.Column(db.String(64), unique=True, nullable=False)


class Customer(Base_model):
    __tablename__ = 'base_customer'
    __info__ = ''' 客户
        除过滤功能外，计划用于报告功能统计业务数据
        '''
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)


# 最后引入模型事件
from . import models_events