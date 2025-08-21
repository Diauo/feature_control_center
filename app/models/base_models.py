from app import db
from datetime import datetime


class Base_model(db.Model):
    __tablename__ = "base"
    __abstract__ = True  # 标记为抽象类，不会映射到具体的表

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    created_date = db.Column(db.DateTime, default=datetime.now)
    updated_date = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def save(self):
        db.session.add(self)
        db.session.commit()
        return self

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def __repr__(self):
        name = getattr(self, 'name', '无名model')
        return f"<{name}>"
    
    def to_dict(self):
        """
        将模型实例转换为字典
        :return: 字典表示的模型数据
        """
        data = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            # 如果是datetime类型，格式化为字符串
            if isinstance(value, datetime):
                # 确保时间格式统一为 yyyy-MM-dd HH:mm:ss
                data[column.name] = value.strftime('%Y-%m-%d %H:%M:%S')
            else:
                data[column.name] = value
        return data


class Feature(Base_model):
    __tablename__ = 'base_feature'
    __info__ = ''' 功能
        一段轻量化可移植的代码逻辑
    '''
    name = db.Column(db.String(64), unique=False, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)
    customer_id = db.Column(db.Integer, unique=False, nullable=False)
    category_id = db.Column(db.Integer, unique=False, nullable=False)
    feature_file_name = db.Column(db.String(256), unique=False, nullable=True)
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
    expanded = False
    selected = False

class Customer(Base_model):
    __tablename__ = 'base_customer'
    __info__ = ''' 客户
        除过滤功能外，计划用于报告功能统计业务数据
        '''
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)

class Config(Base_model):
    __tablename__ = 'base_config'
    __info__ = ''' 配置
        用于管理系统和功能附加的配置项。
        feature_id: 关联的功能id，0表示系统固定配置
    '''
    name = db.Column(db.String(64), unique=False, nullable=False)
    value = db.Column(db.String(256), unique=False, nullable=True)
    default_value = db.Column(db.String(256), unique=False, nullable=True)
    description = db.Column(db.String(256), unique=False, nullable=True)
    feature_id = db.Column(db.Integer, unique=False, nullable=False, default=0)
    feature_name = ""


class FeatureExecutionLog(Base_model):
    __tablename__ = 'feature_execution_log'
    __info__ = ''' 功能执行日志
        记录每次功能执行的结果信息
    '''
    feature_id = db.Column(db.Integer, unique=False, nullable=False)
    request_id = db.Column(db.String(64), unique=True, nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), unique=False, nullable=True)  # 运行中/成功/失败
    client_id = db.Column(db.String(64), unique=False, nullable=True)
    execution_type = db.Column(db.String(16), unique=False, nullable=False, default="manual")  # manual/scheduled
    
    # 关联功能名称，便于查询
    feature_name = ""

class FeatureExecutionLogDetail(Base_model):
    __tablename__ = 'feature_execution_log_detail'
    __info__ = ''' 功能执行日志明细
        记录每次功能执行的详细运行时日志信息
    '''
    log_id = db.Column(db.Integer, unique=False, nullable=False)  # 关联FeatureExecutionLog的ID
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    level = db.Column(db.String(16), unique=False, nullable=True)  # 日志级别 INFO/WARN/ERROR
    message = db.Column(db.Text, unique=False, nullable=True)
    request_id = db.Column(db.String(64), unique=False, nullable=False)
 
class ScheduledTask(Base_model):
    __tablename__ = 'scheduled_task'
    __info__ = ''' 定时任务
        用于定时执行功能的计划任务
    '''
    feature_id = db.Column(db.Integer, unique=False, nullable=False)
    name = db.Column(db.String(64), unique=False, nullable=False)
    description = db.Column(db.String(256), unique=False, nullable=True)
    cron_expression = db.Column(db.String(64), unique=False, nullable=False)
    is_active = db.Column(db.Boolean, unique=False, nullable=False, default=False)
    last_run_time = db.Column(db.DateTime, nullable=True)
    next_run_time = db.Column(db.DateTime, nullable=True)
    
    # 关联功能名称，便于查询
    feature_name = ""

# 最后引入模型事件
from . import models_events