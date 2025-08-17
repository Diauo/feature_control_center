import hashlib
from datetime import datetime


def generate_signature(params, secret):
    # 过滤掉sign参数、byte[]类型参数和app_act参数
    filtered_params = {k: v for k, v in params.items(
    ) if k != 'sign' and not isinstance(v, bytes) and k != 'app_act'}

    # 按照参数名的ASCII码表顺序排序
    sorted_params = sorted(filtered_params.items())

    # 拼装参数名和参数值
    assembled_str = ''.join(f'{k}{v}' for k, v in sorted_params)

    # 拼装前后加上secret
    sign_str = f'{secret}{assembled_str}{secret}'

    # 进行MD5加密
    md5_hash = hashlib.md5(sign_str.encode('utf-8')).hexdigest().upper()

    return md5_hash


def assembly_request_body(method, key, secret, data):
    params = {
        "method": method,
        "format": "json",
        "key": key,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "v": "2.0",
        "sign_method": "md5",
        "data": '{' + ','.join([f'"{k}":"{v}"' for k, v in data.items()]) + "}"
    }
    signature = generate_signature(params, secret)
    params["sign"] = signature
    return params
