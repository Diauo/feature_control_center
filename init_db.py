from app import create_app, db
from app.models.base_models import *
app = create_app()

with app.app_context():
    db.create_all()  # 创建所有表
    print("数据库初始化完成！")
