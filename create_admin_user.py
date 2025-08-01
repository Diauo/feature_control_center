from app import create_app, db
from app.models.user_models import User

app = create_app()

with app.app_context():
    # 检查是否已存在admin用户
    admin_user = User.query.filter_by(username='admin').first()
    if admin_user:
        print(f"Admin user already exists with ID: {admin_user.id}")
        # 更新密码
        admin_user.set_password('admin123')
        db.session.commit()
        print("Admin password updated successfully")
    else:
        # 创建新的admin用户
        admin_user = User(
            username='admin',
            role='admin',
            email='admin@example.com'
        )
        admin_user.set_password('admin123')
        db.session.add(admin_user)
        db.session.commit()
        print(f"Admin user created successfully with ID: {admin_user.id}")