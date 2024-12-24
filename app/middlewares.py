from flask import request, jsonify

def log_request(app):
    @app.before_request
    def log_path():
        print(f"全局请求路径：{request.path}")

# 格式化所有返回值
def global_result_format(app):
    @app.after_request
    def result_format(response):
        # 只处理API的返回值
        if request.path.startswith("/api"):
            # 获取响应的原始数据
            response_data = response.get_json()
            status = response.status_code == 200
            wrapped_response = {
                "status": status,
                "code" : response.status_code,
                "data": response_data if response_data else response.get_data().decode()
            }
            response.set_data(jsonify(wrapped_response).data)
        return response
    
# 异常处理
def exception_handler(app):
    @app.errorhandler(Exception)
    def handle_exception(e):
        # 默认异常返回值
        wrapped_response = {
            "status": False,
            "code" : 500,
            "data": f"{type(Exception).__name__}：{Exception}"
        }
        return jsonify(wrapped_response), 500