from app import create_app, db
from app.models.user_models import User

app = create_app()

with app.app_context():
    users = User.query.all()
    for user in users:
        print(f'User ID: {user.id}, Username: {user.username}, Role: {user.role}, Password hash: {user.password_hash}')