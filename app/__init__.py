from flask import Flask
from app.middlewares import *

from .ws_server import socketio
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app(config_class='app.config.Config'):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 修改 Jinja2 的分隔符
    app.jinja_env.variable_start_string = "[|"
    app.jinja_env.variable_end_string = "|]"


    # 注册蓝图
    from app.controllers.index_controller import index_bp
    app.register_blueprint(index_bp)
    from app.controllers.feature_controller import feature_bp
    app.register_blueprint(feature_bp, url_prefix='/api/feat')
    from app.controllers.customer_controller import customer_bp
    app.register_blueprint(customer_bp, url_prefix='/api/cust')
    from app.controllers.category_controller import category_bp
    app.register_blueprint(category_bp, url_prefix='/api/cate')

    # 注册中间件    
    log_request(app)
    global_result_format(app)
    exception_handler(app)

    # 初始化数据库
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # 注册功能扫描模块
    from app.services.feature_register_service import init_feature_register
    init_feature_register(app)

        
    return app

def run_with_socketio(app):
    socketio.init_app(app)
    socketio.run(app, host="0.0.0.0", port=5000)