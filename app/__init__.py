from flask import Flask
from app.middlewares import log_request, add_custom_header

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config')
    
    # 修改 Jinja2 的分隔符
    app.jinja_env.variable_start_string = "[|"
    app.jinja_env.variable_end_string = "|]"


    # 注册蓝图
    from app.controllers.index_controller import index_bp
    app.register_blueprint(index_bp)
    from app.controllers.feature_controller import feature_bp
    app.register_blueprint(feature_bp, url_prefix='/feat')
    from app.controllers.customer_controller import customer_bp
    app.register_blueprint(customer_bp, url_prefix='/cust')

    # 注册中间件    
    log_request(app)
    add_custom_header(app)

    # 初始化数据库
    db.init_app(app)
    return app