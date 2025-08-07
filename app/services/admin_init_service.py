from app.models.user_models import User
from app import db
import logging

logger = logging.getLogger(__name__)

def create_default_admin():
    """
    检查并创建默认管理员账户
    用户名: overlord
    密码: ExtraLarge@9910
    """
    # 检查是否已存在管理员账户
    admin_user = User.query.filter(
        (User.role == 'admin') & (User.username == 'overlord')
    ).first()
    
    if admin_user:
        logger.info("默认管理员账户已存在")
        return admin_user
    else:
        # 检查是否有任何管理员账户
        any_admin = User.query.filter_by(role='admin').first()
        if any_admin:
            logger.info("系统中已存在其他管理员账户")
            return any_admin
        
        # 创建默认管理员账户
        admin_user = User(
            username='overlord',
            role='admin',
            email='overlord@geu.com',
            is_active=True
        )
        admin_user.set_password('ExtraLarge@9910')
        
        try:
            db.session.add(admin_user)
            db.session.commit()
            logger.info(f"默认管理员账户创建成功，用户ID: {admin_user.id}")
            return admin_user
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建默认管理员账户失败: {str(e)}")
            raise