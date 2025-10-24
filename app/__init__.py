from flask import Flask
from app.middlewares import *
from flask_jwt_extended import JWTManager

from .ws_server import socketio
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app(config_class='app.config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 修改 Jinja2 的分隔符
    app.jinja_env.variable_start_string = "[|"
    app.jinja_env.variable_end_string = "|]"

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

    # 注册蓝图
    from app.controllers.index_controller import index_bp
    app.register_blueprint(index_bp)
    from app.controllers.feature_controller import feature_bp
    app.register_blueprint(feature_bp, url_prefix='/api/feat')
    from app.controllers.customer_controller import customer_bp
    app.register_blueprint(customer_bp, url_prefix='/api/cust')
    from app.controllers.category_controller import category_bp
    app.register_blueprint(category_bp, url_prefix='/api/cate')
    from app.controllers.user_controller import user_bp
    app.register_blueprint(user_bp)
    from app.controllers.config_controller import config_bp
    app.register_blueprint(config_bp, url_prefix='/api/config')
    from app.controllers.log_controller import log_bp
    app.register_blueprint(log_bp, url_prefix='/api/log')
    from app.controllers.scheduled_task_controller import scheduled_task_bp
    app.register_blueprint(scheduled_task_bp, url_prefix='/api/scheduled-task')
    from app.controllers.admin_controller import admin_bp
    app.register_blueprint(admin_bp)

    # 注册中间件
    log_request(app)
    jwt_middleware(app)
    global_result_format(app)
    app_exception_handler(app)

    # 初始化数据库
    db.init_app(app)
    with app.app_context():
        db.create_all()
        
        # 检查并创建默认管理员账户
        try:
            from app.services.admin_init_service import create_default_admin
            create_default_admin()
        except Exception as e:
            print(f"创建默认管理员账户时出错: {str(e)}")
        
        # 检查并创建默认客户
        try:
            from app.services.customer_service import create_default_customer
            create_default_customer()
        except Exception as e:
            print(f"创建默认客户时出错: {str(e)}")
        
        # 初始化和启动定时任务调度器
        try:
            from app.scheduler import task_scheduler
            task_scheduler.init_app(app)  # 初始化调度器的应用实例
            task_scheduler.start()
            task_scheduler.load_scheduled_tasks()
            print("定时任务调度器已启动")
        except Exception as e:
            print(f"启动定时任务调度器时出错: {str(e)}")
        
    return app

def run_with_socketio(app):
    socketio.init_app(app)
    socketio.run(app, host="0.0.0.0", port=5000, allow_unsafe_werkzeug=True)