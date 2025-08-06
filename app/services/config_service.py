from app import db
from sqlalchemy import text
from app.models.base_models import Config, Feature
from app.util.serviceUtil import model_to_dict
import logging

def get_all_config():
    try:
        sql = text('''
            select * from base_config
        ''')
        result = db.session.execute(sql).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置列表失败: {str(e)}")
        return False, f"获取配置列表失败: {str(e)}", []

def get_config_by_id(config_id):
    if config_id is None:
        return False, "config_id为空", []
    try:
        sql = text('''
            select * from base_config where id = :config_id
        ''')
        result = db.session.execute(sql, {'config_id': config_id}).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置失败: {str(e)}")
        return False, f"获取配置失败: {str(e)}", []

def get_config_by_feature_id(feature_id):
    if feature_id is None:
        return False, "feature_id为空", []
    try:
        sql = text('''
            select * from base_config where feature_id = :feature_id
        ''')
        result = db.session.execute(sql, {'feature_id': feature_id}).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置失败: {str(e)}")
        return False, f"获取配置失败: {str(e)}", []

def add_config(config):
    try:
        db.session.add(config)
        db.session.commit()
        logging.info(f"成功添加配置: {config.name}")
        return True, "添加成功", config.to_dict()
    except Exception as e:
        db.session.rollback()
        logging.error(f"添加配置失败: {str(e)}")
        return False, f"添加配置失败: {str(e)}", None

def update_config(config_id, update_dict):
    try:
        config = Config.query.get(config_id)
        if not config:
            return False, "未找到配置", None
        for k, v in update_dict.items():
            setattr(config, k, v)
        db.session.commit()
        logging.info(f"成功更新配置: {config.name}")
        return True, "更新成功", config.to_dict()
    except Exception as e:
        db.session.rollback()
        logging.error(f"更新配置失败: {str(e)}")
        return False, f"更新配置失败: {str(e)}", None

def delete_config(config_id):
    try:
        config = Config.query.get(config_id)
        if not config:
            return False, "未找到配置", None
        # 如果是feature配置，校验feature是否存在
        if config.feature_id != 0:
            feature = Feature.query.get(config.feature_id)
            if feature:
                return False, "该配置关联的功能仍存在，不能删除", None
        db.session.delete(config)
        db.session.commit()
        logging.info(f"成功删除配置: {config_id}")
        return True, "删除成功", None
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除配置失败: {str(e)}")
        return False, f"删除配置失败: {str(e)}", None

def delete_config_by_feature_id(feature_id):
    if feature_id is None:
        return False, "feature_id为空", None
    try:
        configs = Config.query.filter_by(feature_id=feature_id).all()
        if not configs:
            return True, "没有找到相关配置", None
        for config in configs:
            db.session.delete(config)
        db.session.commit()
        logging.info(f"成功删除功能 {feature_id} 的相关配置")
        return True, "删除相关配置成功", None
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除相关配置失败: {str(e)}")
        return False, f"删除相关配置失败: {str(e)}", None

def reload_config():
    try:
        # 这里可以根据实际需求实现配置重载逻辑
        # 比如重新加载到内存、刷新缓存等
        # 这里只做简单示例
        configs = Config.query.all()
        config_dict = {c.name: c.value for c in configs}
        # 假设有全局变量或缓存需要更新
        # global_config.update(config_dict)
        logging.info("配置重载成功")
        return True, "配置重载成功", config_dict
    except Exception as e:
        logging.error(f"配置重载失败: {str(e)}")
        return False, f"配置重载失败: {str(e)}", {}

def cleanup_invalid_config():
    """
    清理无效配置
    清理那些已经没有关联功能的配置（feature_id不为0但对应功能不存在的配置）
    """
    try:
        # 查询所有feature_id不为0的配置
        configs = Config.query.filter(Config.feature_id != 0).all()
        
        deleted_count = 0
        
        for config in configs:
            # 检查关联的功能是否存在
            feature = Feature.query.get(config.feature_id)
            if not feature:
                # 功能不存在，删除配置
                db.session.delete(config)
                deleted_count += 1
        
        # 提交更改
        db.session.commit()
        logging.info(f"清理无效配置完成，共删除{deleted_count}个无效配置")
        
        return True, f"清理完成，共删除{deleted_count}个无效配置", deleted_count
    except Exception as e:
        db.session.rollback()
        logging.error(f"清理无效配置失败: {str(e)}")
        return False, f"清理无效配置失败: {str(e)}", 0