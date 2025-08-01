from flask import Blueprint, jsonify, request, render_template, send_file, redirect, url_for
import os

index_bp = Blueprint('index', __name__)

@index_bp.route('/', methods=['GET'])
def index():
    # 检查用户是否已登录（简化检查，实际应用中可能需要更复杂的逻辑）
    # 这里我们直接渲染主页，前端会处理认证逻辑
    return render_template("index.html")


@index_bp.route('/login', methods=['GET'])
def login():
    return render_template("login.html")


@index_bp.route('/favicon.ico', methods=['GET'])
def favicon():
    return send_file("favicon.ico")

@index_bp.before_request
def joke():
    user_agent = request.headers.get('User-Agent')
    print(f"{user_agent}用户，欢迎来到首页")
    current_directory = os.getcwd()
    print(f'当前工作目录: {current_directory}')