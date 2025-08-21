from app import create_app
from app.models.base_models import Feature

def list_features():
    app = create_app()
    with app.app_context():
        features = Feature.query.all()
        print('Available features:')
        for f in features:
            print(f'{f.id}: {f.name}')

if __name__ == '__main__':
    list_features()