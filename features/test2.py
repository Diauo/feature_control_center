__meta__ = {
    "name": "(• •)",
    "description": "看我干什么",
    "customer": "地能",
    "configs": {
        "appid": (None, "应用ID"),  # 默认值，如果为None则意味着是必填
        "days": ("3", "天数")  # 有默认值，没配置的情况下就用默认值
    }
}

def run(params, config):
    print("Hello World")