from flask import Blueprint, jsonify, request, render_template, send_file
import os

index_bp = Blueprint('index', __name__)

@index_bp.route('/', methods=['GET'])
def index():
    return render_template("index.html")


@index_bp.route('/favicon.ico', methods=['GET'])
def favicon():
    return send_file("favicon.ico")

@index_bp.before_request
def joke():
    user_agent = request.headers.get('User-Agent')
    print(f"{user_agent}用户，欢迎来到首页")
    current_directory = os.getcwd()
    print(f'当前工作目录: {current_directory}')