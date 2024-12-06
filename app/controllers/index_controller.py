from flask import Blueprint, jsonify, request, render_template

index_bp = Blueprint('index', __name__)

@index_bp.route('/', methods=['GET'])
def index():
    return render_template("index.html")


@index_bp.before_request
def joke():
    user_agent = request.headers.get('User-Agent')
    print(f"{user_agent}用户，欢迎来到首页")