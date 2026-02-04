from app import db
from sqlalchemy import text
from app.models.base_models import Config, Feature


def _resolve_customer_id_for_feature(feature_id: int) -> int:
    """Resolve customer_id for a given feature.

    - feature_id == 0 => system/global config (customer_id = 0)
    - otherwise => take from base_feature.customer_id
    """
    if int(feature_id) == 0:
        return 0
    feature = Feature.query.get(int(feature_id))
    if not feature:
        raise ValueError(f"未找到ID为[{feature_id}]的功能")
    return int(feature.customer_id)
from app.util.serviceUtil import model_to_dict
import logging

def get_all_config():
    try:
        sql = text('''
            SELECT c.*, f.name as feature_name
            FROM base_config c
            LEFT JOIN base_feature f ON c.feature_id = f.id
        ''')
        result = db.session.execute(sql).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置列表失败: {str(e)}")
        return False, f"获取配置列表失败: {str(e)}", []

def get_filtered_config(feature_id=None, feature_name=None, config_name=None, config_description=None):
    try:
        # 构建SQL查询
        sql = '''
            SELECT c.*, f.name as feature_name
            FROM base_config c
            LEFT JOIN base_feature f ON c.feature_id = f.id
            WHERE 1=1
        '''
        params = {}
        
        # 添加筛选条件
        if feature_id is not None:
            if feature_id == 0:  # 系统配置
                sql += ' AND c.feature_id = 0'
            else:  # 特定功能配置
                sql += ' AND c.feature_id = :feature_id'
                params['feature_id'] = feature_id
                
        if feature_name:
            sql += ' AND f.name LIKE :feature_name'
            params['feature_name'] = f'%{feature_name}%'
            
        if config_name:
            sql += ' AND c.name LIKE :config_name'
            params['config_name'] = f'%{config_name}%'
            
        if config_description:
            sql += ' AND c.description LIKE :config_description'
            params['config_description'] = f'%{config_description}%'
        
        # 执行查询
        result = db.session.execute(text(sql), params).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取筛选配置列表失败: {str(e)}")
        return False, f"获取筛选配置列表失败: {str(e)}", []

def get_config_by_id(config_id):
    if config_id is None:
        return False, "config_id为空", []
    try:
        sql = text('''
            SELECT c.*, f.name as feature_name
            FROM base_config c
            LEFT JOIN base_feature f ON c.feature_id = f.id
            WHERE c.id = :config_id
        ''')
        result = db.session.execute(sql, {'config_id': config_id}).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置失败: {str(e)}")
        return False, f"获取配置失败: {str(e)}", []

def get_config_by_feature_id(feature_id, customer_id=None):
    """按功能获取配置。

    当 customer_id 提供时，返回该客户在该功能下的配置，实现客户隔离。
    """
    if feature_id is None:
        return False, "feature_id为空", []
    try:
        sql = '''
            SELECT c.*, f.name as feature_name
            FROM base_config c
            LEFT JOIN base_feature f ON c.feature_id = f.id
            WHERE c.feature_id = :feature_id
        '''
        params = {'feature_id': feature_id}

        if customer_id is not None:
            sql += ' AND c.customer_id = :customer_id'
            params['customer_id'] = int(customer_id)

        result = db.session.execute(text(sql), params).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置失败: {str(e)}")
        return False, f"获取配置失败: {str(e)}", []

def add_config(config):
    try:
        # 客户隔离：根据 feature_id 绑定 customer_id
        config.customer_id = _resolve_customer_id_for_feature(config.feature_id)

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

        # 不允许前端直接改 customer_id，强制由 feature_id 推导
        if 'customer_id' in update_dict:
            update_dict = dict(update_dict)
            update_dict.pop('customer_id', None)

        for k, v in update_dict.items():
            setattr(config, k, v)

        # 客户隔离：若 feature_id 变更或历史数据缺失 customer_id，则重新绑定
        config.customer_id = _resolve_customer_id_for_feature(config.feature_id)

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
    '''
    目前并没有重载配置的需求，但是预留一个接口
    '''
    try:
        logging.info("配置重载成功")
        return True, "配置重载成功", {}
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