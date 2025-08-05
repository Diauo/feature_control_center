# 配置管理服务设计

## 服务文件
`app/services/config_service.py`

## 服务实现

基于现有的配置服务，我们需要添加清理无效配置的功能：

```python
from app import db
from sqlalchemy import text
from app.models.base_models import Config, Feature
from app.util.serviceUtil import model_to_dict

def get_all_config():
    sql = text('''
        select * from base_config
    ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Config)

def get_config_by_id(config_id):
    if config_id is None:
        return False, "config_id为空", []
    sql = text('''
        select * from base_config where id = :config_id
    ''')
    result = db.session.execute(sql, {'config_id': config_id}).fetchall()
    return True, "成功", model_to_dict(result, Config)

def get_config_by_feature_id(feature_id):
    if feature_id is None:
        return False, "feature_id为空", []
    sql = text('''
        select * from base_config where feature_id = :feature_id
    ''')
    result = db.session.execute(sql, {'feature_id': feature_id}).fetchall()
    return True, "成功", model_to_dict(result, Config)

def add_config(config):
    db.session.add(config)
    db.session.commit()
    return True, "添加成功", config.to_dict()

def update_config(config_id, update_dict):
    config = Config.query.get(config_id)
    if not config:
        return False, "未找到配置", None
    for k, v in update_dict.items():
        setattr(config, k, v)
    db.session.commit()
    return True, "更新成功", config.to_dict()

def delete_config(config_id):
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
    return True, "删除成功", None

def delete_config_by_feature_id(feature_id):
    if feature_id is None:
        return False, "feature_id为空", None
    configs = Config.query.filter_by(feature_id=feature_id).all()
    if not configs:
        return True, "没有找到相关配置", None
    for config in configs:
        db.session.delete(config)
    db.session.commit()
    return True, "删除相关配置成功", None

def reload_config():
    # 这里可以根据实际需求实现配置重载逻辑
    # 比如重新加载到内存、刷新缓存等
    # 这里只做简单示例
    configs = Config.query.all()
    config_dict = {c.name: c.value for c in configs}
    # 假设有全局变量或缓存需要更新
    # global_config.update(config_dict)
    return True, "配置重载成功", config_dict

def cleanup_invalid_config():
    """
    清理无效配置
    清理那些已经没有关联功能的配置（feature_id不为0但对应功能不存在的配置）
    """
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
    
    return True, f"清理完成，共删除{deleted_count}个无效配置", deleted_count