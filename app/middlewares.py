from flask import request

def log_request(app):
    @app.before_request
    def log_path():
        print(f"全局请求路径：{request.path}")

def add_custom_header(app):
    @app.after_request
    def modify_response(response):
        response.headers['X-Custom-Header'] = 'FlaskMiddleware'
        return response
