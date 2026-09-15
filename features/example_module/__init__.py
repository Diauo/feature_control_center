__meta__ = {
    "name": "示例模块",
    "description": "这是一个示例模块，演示如何注册和执行带有多个Python文件的模块。",
    "customer": "默认客户",
    "configs": {
        "greeting": ("Hello", "问候语"),
        "target": ("World", "目标")
    }
}

from . import utils
from . import config

def run(configs, ctx):
    """
    模块的主执行函数
    :param configs: 配置字典
    :param ctx: 执行上下文
    :return: (bool, str, dict) 是否成功，提示信息，返回数据
    """
    try:
        ctx.log("开始执行示例模块")
        
        # 获取配置
        greeting = configs.get("greeting", "Hello")
        target = configs.get("target", "World")
        
        # 使用辅助函数
        message = utils.create_greeting(greeting, target)
        
        # 记录日志
        ctx.log(f"生成的消息: {message}")
        
        # 返回结果
        result = {
            "message": message,
            "config": configs,
            "module_info": config.MODULE_INFO
        }
        
        ctx.log("示例模块执行成功")
        return True, "执行成功", result
    except Exception as e:
        ctx.log(f"执行失败: {str(e)}", "error")
        return False, f"执行失败: {str(e)}", None