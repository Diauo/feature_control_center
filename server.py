from flask import render_template
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
    
# 测试二次提交的用户信息
