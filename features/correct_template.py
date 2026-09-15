from app.util.feature_execution_context import FeatureExecutionContext

__meta__ = {
    "name": "Hello World",
    "description": "打印Hello World",
    "customer": "天能",
    "configs": {
        "appid": ("114514", "应用ID"),  # 默认值，如果为None则意味着是必填
        "days": ("3", "天数")  # 有默认值，没配置的情况下就用默认值
    }
}

def run(config: dict, ctx: FeatureExecutionContext):
    ctx.log("Hello World")
    ctx.log(f"配置参数: {config}")
    return True, "执行成功", {"message": "Hello World"}