from flask import Blueprint, render_template
from app.middlewares import require_role

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin', methods=['GET'])
@require_role('admin')
def admin_page():
    """
    渲染业务管理页面
    """
    return render_template("admin.html")