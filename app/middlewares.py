from flask import request, jsonify

def log_request(app):
    @app.before_request
    def log_path():
        print(f"全局请求路径：{request.path}")

# 格式化所有返回值
def global_result_format(app):
    @app.after_request
    def result_format(response):
        # 只处理 JSON 响应
        if response.is_json:
            # 获取响应的原始数据
            response_data = response.get_json()
            status = response.status_code == 200
            wrapped_response = {
                "status": status,
                "code" : response.status_code,
                "data": response_data
            }
            response.set_data(jsonify(wrapped_response).data)
        return response