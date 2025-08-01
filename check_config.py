from app import create_app

app = create_app()

with app.app_context():
    print(f"JWT_SECRET_KEY: {app.config.get('JWT_SECRET_KEY')}")
    print(f"SQLALCHEMY_DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI')}")