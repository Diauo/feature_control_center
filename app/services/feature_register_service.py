import os
import time
import threading
import importlib.util
from app.services import feature_service, customer_service, config_service
from app import db
from app.models.base_models import Feature, Config
from app.util.log_utils import logger

FEATURE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../features"))
UPLOADED_FEATURE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploaded_features"))
SCAN_INTERVAL = 60  # 每60秒全量扫描一次

def load_feature_meta(script_path):
    try:
        if os.path.isfile(script_path) and script_path.endswith('.py'):
            # 处理单个.py文件
            spec = importlib.util.spec_from_file_location("feature_module", script_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return getattr(module, "__meta__", None)
        elif os.path.isdir(script_path):
            # 处理模块目录
            init_file = os.path.join(script_path, "__init__.py")
            if os.path.exists(init_file):
                spec = importlib.util.spec_from_file_location("feature_module", init_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return getattr(module, "__meta__", None)
        return None
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
        fpath = os.path.join(FEATURE_DIR, fname)
        # 检查是否为目录且包含__init__.py
        if os.path.isdir(fpath) and os.path.exists(os.path.join(fpath, "__init__.py")):
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
                    feature_file_name=f"features/{fname}",
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
        elif os.path.isfile(fpath) and fname.endswith(".py"):
            # 处理单个.py文件
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
                    feature_file_name=f"features/{fname}",
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

def register_uploaded_feature(file_path, name, description, customer_id, category_id):
    """
    注册前端上传的功能脚本
    :param file_path: 上传的功能脚本文件路径
    :param name: 功能名称
    :param description: 功能描述
    :param customer_id: 客户ID
    :param category_id: 分类ID
    :return: (bool, str) 是否成功，提示信息
    """
    try:
        # 1. 加载功能脚本的元数据
        meta = load_feature_meta(file_path)
        if not meta:
            return False, "无法加载功能脚本元数据"
        
        # 2. 检查功能名称是否已存在
        _, _, db_features = feature_service.get_all_feature()
        db_feature_names = set(f['name'] for f in db_features)
        if name in db_feature_names:
            return False, f"功能名称 '{name}' 已存在"
        
        # 3. 获取客户ID（如果提供了客户名称）
        if meta.get("customer"):
            customer_name = meta.get("customer")
            ok, _, customers = customer_service.get_customer_by_name(customer_name)
            if ok and customers:
                customer_id = customers[0].get("id", 0)
            else:
                logger.warning(f"未找到客户: {customer_name}，将使用传入的customer_id={customer_id}")
        
        # 4. 获取文件名
        filename = os.path.basename(file_path)
        if os.path.isdir(file_path):
            filename = os.path.basename(os.path.dirname(file_path)) if file_path.endswith(os.sep) else os.path.basename(file_path)
        
        # 5. 注册功能到数据库
        feature = Feature(
            name=name,
            description=description or meta.get("description", ""),
            feature_file_name=f"uploaded_features/{filename}",
            customer_id=customer_id or 0,
            category_id=category_id or 0
        )
        _, msg, feature_data = feature_service.add_feature(feature)
        if not _:
            return False, f"添加功能到数据库失败: {msg}"
        
        feature_id = feature_data.get('id')
        
        # 6. 读取元数据中的所有配置项并注册到数据库
        added_configs = []  # 记录已添加的配置项，用于回滚
        try:
            for config_name, config_value in meta.get("configs", {}).items():
                if isinstance(config_value, tuple):
                    config_value, config_description = config_value
                else:
                    config_description = config_name
                config = Config(
                    name=config_name,
                    default_value=config_value,
                    description=config_description,
                    feature_id=feature_id
                )
                _, config_msg, config_data = config_service.add_config(config)
                if not _:
                    raise Exception(f"添加配置项 '{config_name}' 失败: {config_msg}")
                added_configs.append(config_data.get('id') if config_data else None)
            
            logger.info(f"上传功能 {name} 注册成功")
            return True, "功能注册成功"
        except Exception as e:
            # 如果配置注册失败，删除已添加的功能和配置
            logger.error(f"注册配置项时出错: {e}")
            
            # 删除已添加的配置项
            for config_id in added_configs:
                if config_id:
                    try:
                        config_service.delete_config(config_id)
                    except Exception as delete_e:
                        logger.error(f"删除配置项 {config_id} 失败: {delete_e}")
            
            # 删除已添加的功能
            try:
                feature_service.delete_feature(feature_id)
            except Exception as delete_e:
                logger.error(f"删除功能 {feature_id} 失败: {delete_e}")
            
            return False, f"功能注册失败: {str(e)}"
    except Exception as e:
        logger.error(f"注册上传功能失败: {e}")
        return False, f"功能注册失败: {str(e)}"
