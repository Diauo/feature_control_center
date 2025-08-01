from app import create_app
from app.services.user_service import generate_tokens
from app.models.user_models import User

app = create_app()

with app.app_context():
    # 获取admin用户
    user = User.query.filter_by(username='admin').first()
    if user:
        # 生成token
        access_token, refresh_token = generate_tokens(user)
        print(f"Access Token: {access_token}")
        print(f"Refresh Token: {refresh_token}")
    else:
        print("Admin user not found")