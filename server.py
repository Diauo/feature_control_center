from app import create_app, run_with_socketio

app = create_app()

if __name__ == '__main__':
    run_with_socketio(app)