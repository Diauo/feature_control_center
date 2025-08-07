import os
import time
import threading
import importlib.util
from app.services import feature_service, customer_service, config_service
from app import db
from app.models.base_models import Feature, Config
from app.util.log_utils import logger

FEATURE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../features"))
SCAN_INTERVAL = 60  # 每60秒全量扫描一次

def load_feature_meta(script_path):
    try:
        spec = importlib.util.spec_from_file_location("feature_module", script_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "__meta__", None)
    except Exception as e:
        logger.warning(f"加载功能脚本失败: {script_path}, 错误: {e}")
        return None

def scan_and_register_features():
    # 1. 获取数据库已有功能
    _, _, db_features = feature_service.get_all_feature()
    db_feature_names = set(f['name'] for f in db_features)
    db_feature_ids = {f['id']: f for f in db_features}
    # 2. 扫描目录
    for fname in os.listdir(FEATURE_DIR):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(FEATURE_DIR, fname)
        meta = load_feature_meta(fpath)
        if not meta or not meta.get("name"):
            continue
        # 3. 如果数据库没有该功能，则注册
        if meta["name"] not in db_feature_names:
            # 4. 获取客户ID
            customer_id = 0
            customer_name = meta.get("customer")
            if customer_name:
                ok, _, customers = customer_service.get_customer_by_name(customer_name)
                if ok and customers:
                    customer_id = customers[0].get("id", 0)
                else:
                    logger.warning(f"未找到客户: {customer_name}，将使用默认customer_id=0")
            logger.info(f"注册新功能: {meta['name']} (客户ID: {customer_id})")
            feature = Feature(
                name=meta["name"],
                description=meta.get("description", ""),
                feature_file_name=fname,
                customer_id=customer_id,
                category_id=0
            )
            feature_service.add_feature(feature)
            # 读取元数据中的所有配置项
            for config_name, config_value in meta.get("configs", {}).items():
                if isinstance(config_value, tuple):
                    config_value, config_description = config_value
                else:
                    config_description = config_name
                config = Config(
                    name=config_name,
                    default_value=config_value,
                    description=config_description,
                    feature_id=feature.id
                )
                config_service.add_config(config)
        else:
            feature_id = next((f['id'] for f in db_features if f['name'] == meta["name"]), None)
            # 移除db_feature_ids中已处理的功能，以便删除未在脚本中定义的功能
            db_feature_ids.pop(feature_id, None)
    # 5. 删除数据库中未在脚本中定义的功能
    for feature_id, feature in db_feature_ids.items():
        logger.info(f"删除未定义功能: {feature['name']} (ID: {feature_id})")
        feature_service.delete_feature(feature_id)
        # 删除相关配置
        config_service.delete_config_by_feature_id(feature_id)
