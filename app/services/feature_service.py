from app import db
from sqlalchemy import text
from app.models.base_models import Feature
from app.util.serviceUtil import model_to_dict
import importlib.util
import os
from app.services import feature_service, config_service
from app.util.log_utils import logger
from app.util.feature_execution_context import FeatureExecutionContext
from flask import current_app
import threading
import time
import zipfile
import shutil

def get_all_feature():
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_customer_id(customer_id):
    if customer_id is None:
        return False, "客户ID[customer_id]为空", []
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                where ct.id = :customer_id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_category_id(category_id, customer_id=None):
    if category_id is None:
        return False, "分类ID[category_id]为空", []
    
    # 构建基础SQL查询
    sql_str = '''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                where ft.category_id = :category_id
               '''
    
    # 如果提供了customer_id，则添加到查询条件中
    params = {'category_id': category_id}
    if not customer_id in [None, '']:
        sql_str += ' and ft.customer_id = :customer_id'
        params['customer_id'] = customer_id
    
    sql_str += ' group by ft.id, ct.id'
    
    sql = text(sql_str)
    result = db.session.execute(sql, params).fetchall()
    return True, "成功", model_to_dict(result, Feature)
def add_feature(feature):
    """
    添加新功能
    :param feature: Feature对象
    :return: (bool, str, dict) 是否成功，提示信息，添加后的数据
    """
    db.session.add(feature)
    db.session.commit()
    return True, "添加成功", feature.to_dict()

def update_feature(feature_id, name=None, description=None, customer_id=None, category_id=None):
    """
    更新指定feature_id的功能信息
    :param feature_id: 功能ID
    :param name: 功能名称
    :param description: 功能描述
    :param customer_id: 客户ID
    :param category_id: 分类ID
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    feature = Feature.query.get(feature_id)
    if not feature:
        return False, f"未找到ID为[{feature_id}]的功能", None
    if name is not None:
        feature.name = name
    if description is not None:
        feature.description = description
    if customer_id is not None:
        feature.customer_id = customer_id
    if category_id is not None:
        feature.category_id = category_id
    db.session.commit()
    return True, "更新成功", feature.to_dict()

def delete_feature(feature_id):
    """
    删除指定feature_id的功能
    :param feature_id: 功能ID
    :return: (bool, str) 是否成功，提示信息
    """
    feature = Feature.query.get(feature_id)
    if not feature:
        return False, f"未找到ID为[{feature_id}]的功能"
    
    # 1. 删除相关配置
    from app.services import config_service
    config_service.delete_config_by_feature_id(feature_id)
    
    # 2. 删除功能文件
    try:
        if feature.feature_file_name:
            # 获取项目根目录
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
            # 拼接文件路径
            file_path = os.path.join(base_dir, feature.feature_file_name)
            # 如果文件或目录存在则删除
            if os.path.exists(file_path):
                # 检查是否为目录
                if os.path.isdir(file_path):
                    # 删除目录及其所有内容
                    shutil.rmtree(file_path, ignore_errors=True)
                else:
                    # 删除文件
                    # 先尝试修改文件权限以避免"拒绝访问"错误
                    # 在Windows上，os.chmod的行为与Linux不同，所以我们需要更谨慎地处理
                    try:
                        import stat
                        # 获取当前文件权限
                        current_permissions = os.stat(file_path).st_mode
                        # 添加写权限
                        os.chmod(file_path, current_permissions | stat.S_IWRITE)
                    except:
                        # 如果修改权限失败，继续尝试删除
                        pass
                    
                    # 尝试删除文件
                    try:
                        os.remove(file_path)
                    except PermissionError:
                        # 如果是权限错误，尝试使用更强制的方式
                        import stat
                        os.chmod(file_path, stat.S_IWRITE)
                        os.remove(file_path)
    except Exception as e:
        logger.error(f"删除功能文件失败: {e}，继续删除数据库记录")
    
    # 3. 删除数据库记录
    db.session.delete(feature)
    db.session.commit()
    return True, "删除成功"

def get_feature_by_id(feature_id):
    """
    根据功能ID获取功能信息
    :param feature_id: 功能ID
    :return: (bool, str, dict) 是否成功，提示信息，功能数据
    """
    feature = Feature.query.get(feature_id)
    if not feature:
        return False, f"未找到ID为[{feature_id}]的功能", None
    return True, "成功", feature.to_dict()

def execute_feature(feature_id, client_id, execution_type="manual"):
    # 1. 查询功能信息
    ok, msg, feature = feature_service.get_feature_by_id(feature_id)
    if not ok:
        return False, f"查询功能失败: {msg}", None

    # 2. 获取项目根目录
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))

    # 3. 拼接脚本路径
    feature_file_name = feature.get('feature_file_name', '')
    if not feature_file_name:
        return False, "功能脚本文件名为空", None
    
    script_path = os.path.join(base_dir, feature_file_name)
    
    # 4. 检查路径是文件还是目录
    if os.path.isdir(script_path):
        # 如果是目录，检查是否存在__init__.py文件
        init_file = os.path.join(script_path, "__init__.py")
        if not os.path.exists(init_file):
            return False, f"模块目录中缺少__init__.py文件: {script_path}", None
        script_path = init_file
    elif not os.path.isfile(script_path):
        return False, f"功能脚本不存在: {script_path}", None

    # 5. 动态加载并异步执行 run()
    app = current_app._get_current_object()
    def run_feature_script():
        with app.app_context():
            ctx = FeatureExecutionContext(client_id, feature.get("name"), feature_id, execution_type=execution_type)
            # 使用脚本路径生成唯一的模块名
            module_name = f"feature_module_{hash(script_path) & 0x7FFFFFFF}"
            module = None
            try:
                import sys
                # 检查模块是否已经加载过
                if module_name in sys.modules:
                    module = sys.modules[module_name]
                else:
                    spec = importlib.util.spec_from_file_location(module_name, script_path)
                    module = importlib.util.module_from_spec(spec)
                    # 将模块添加到sys.modules中，以支持相对导入
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                if not hasattr(module, "run"):
                    ctx.log(f"{feature.get('name', '未知功能')} 功能脚本缺少 run() 方法，不符合规范", "error", False)
                    ctx.error(f"{feature.get('name', '未知功能')} 功能脚本缺少 run() 方法，不符合规范")
                    return
                config = config_service.get_config_by_feature_id(feature_id)
                config_dict = {
                        c['name']: c['value'] if c.get('value') not in [None, ''] else c.get('default_value')
                        for c in config[2]
                    } if config[0] else {}
                if not config_dict:
                    config_dict = {}
                # 如果配置中存在为空的值，也没有默认值，则认为是无效配置，指出没有值的配置，报错并结束
                if not all(v is not None for v in config_dict.values()):
                    missing_configs = [k for k, v in config_dict.items() if v is None]
                    ctx.log(f"{feature.get('name', '未知功能')} 功能脚本配置无效，缺少值的配置: {missing_configs}", "error", False)
                    ctx.fail(f"{feature.get('name', '未知功能')} 功能脚本配置无效，缺少值的配置: {missing_configs}")
                    return
                # 等待一秒后执行
                time.sleep(1)
                status, msg, data = module.run(config_dict, ctx)
                if status:
                    ctx.log("功能执行成功")
                    ctx.done(msg, data)
                else:
                    ctx.log(f"功能执行失败: {msg}", "error", False)
                    ctx.fail(msg, data)
            except Exception as e:
                ctx.log(f"执行异常：{e}", "error", False)
                ctx.fail(str(e))

    t = threading.Thread(target=run_feature_script)
    t.start()
    msg = "功能已启动，日志和结果将通过WebSocket实时推送" if execution_type=="manual" else "定时任务已启动，执行结果将展示在日志中"
    return True, msg, None

def register_feature(file, name, description, customer_id, category_id):
    """
    注册新功能
    :param file: 上传的功能脚本文件
    :param name: 功能名称
    :param description: 功能描述
    :param customer_id: 客户ID
    :param category_id: 分类ID
    :return: (bool, str) 是否成功，提示信息
    """
    try:
        import os
        from app.util.log_utils import logger
        from app.services.feature_register_service import load_feature_meta
        
        # 1. 获取上传功能目录路径
        uploaded_feature_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../uploaded_features"))
        
        # 2. 确保目录存在
        os.makedirs(uploaded_feature_dir, exist_ok=True)
        
        # 3. 生成文件名
        filename = file.filename
        
        # 4. 保存文件到上传目录
        file_path = os.path.join(uploaded_feature_dir, filename)
        
        # 5. 如果文件已存在，添加时间戳
        if os.path.exists(file_path):
            import time
            name_without_ext = os.path.splitext(filename)[0]
            ext = os.path.splitext(filename)[1]
            filename = f"{name_without_ext}_{int(time.time())}{ext}"
            file_path = os.path.join(uploaded_feature_dir, filename)
        
        file.save(file_path)
        
        # 6. 如果是压缩包，解压到同名目录
        if filename.endswith('.zip'):
            # 创建解压目录
            extract_dir = os.path.join(uploaded_feature_dir, os.path.splitext(filename)[0])
            os.makedirs(extract_dir, exist_ok=True)
            
            # 解压文件
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            #解压完成后删除文件
            os.remove(file_path)

            # 验证解压后的目录是否存在__init__.py文件
            init_file = os.path.join(extract_dir, "__init__.py")
            if not os.path.exists(init_file):
                return False, f"不是有效的功能脚本包，缺少 __init__.py 文件"
            
            # 更新文件路径为解压后的目录
            file_path = extract_dir
        
        # 7. 加载功能脚本的元数据
        meta = load_feature_meta(file_path)
        if not meta:
            # 没有有效的meta数据，删除已保存的文件并报错
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            return False, "无法加载功能脚本元数据，功能模块必须包含有效的__meta__信息"
        
        # 8. 如果前端没有提供名称、描述，则使用meta中的信息
        final_name = name if name else meta.get("name", os.path.splitext(filename)[0])
        final_description = description if description else meta.get("description", "")
        
        # 10. 调用新的功能注册服务注册该文件
        from app.services.feature_register_service import register_uploaded_feature
        status, msg = register_uploaded_feature(file_path, final_name, final_description, customer_id, category_id)
        
        if status:
            logger.info(f"功能文件 {filename} 注册成功")
            return True, "功能注册成功"
        else:
            # 注册失败，删除已保存的文件或目录
            if os.path.exists(file_path):
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            return False, msg
    except Exception as e:
        logger.error(f"功能注册失败: {e}")
        # 删除已保存的文件或目录
        if 'file_path' in locals() and os.path.exists(file_path):
            if os.path.isfile(file_path):
                os.remove(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        return False, f"功能注册失败: {str(e)}"