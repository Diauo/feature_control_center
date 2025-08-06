"""
通用结果返回对象
用于统一控制器的返回值格式
"""

from flask import jsonify
from typing import Any, Optional, Dict, Union
import traceback


class Result:
    """通用结果返回类"""

    def __init__(self, status: bool = True, code: int = 200, data: Any = None, message: str = ""):
        """
        初始化结果对象
        
        :param status: 请求状态 True=成功, False=失败
        :param code: HTTP状态码
        :param data: 返回数据
        :param message: 返回消息
        """
        self.status = status
        self.code = code
        self.data = data
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        """
        将结果对象转换为字典格式
        
        :return: 结果字典
        """
        return {
            "status": self.status,
            "code": self.code,
            "data": self.data,
            "message": self.message
        }

    def to_json(self):
        """
        将结果对象转换为JSON格式响应
        
        :return: Flask JSON响应
        """
        return jsonify(self.to_dict()), 200  # 总是返回200，让前端根据status字段判断业务状态

    @staticmethod
    def success(data: Any = None, message: str = "操作成功", code: int = 200) -> 'Result':
        """
        创建成功结果
        
        :param data: 返回数据
        :param message: 成功消息
        :param code: HTTP状态码
        :return: 成功结果对象
        """
        return Result(status=True, code=code, data=data, message=message).to_json()

    @staticmethod
    def error(message: str = "操作失败", code: int = 500, data: Any = None) -> 'Result':
        """
        创建错误结果
        
        :param message: 错误消息
        :param code: HTTP状态码
        :param data: 返回数据
        :return: 错误结果对象
        """
        return Result(status=False, code=code, data=data, message=message).to_json()

    @staticmethod
    def unauthorized(message: str = "未授权访问") -> 'Result':
        """
        创建未授权结果
        
        :param message: 错误消息
        :return: 未授权结果对象
        """
        return Result.error(message=message, code=401).to_json()

    @staticmethod
    def forbidden(message: str = "权限不足") -> 'Result':
        """
        创建权限不足结果
        
        :param message: 错误消息
        :return: 权限不足结果对象
        """
        return Result.error(message=message, code=403).to_json()

    @staticmethod
    def not_found(message: str = "资源不存在") -> 'Result':
        """
        创建资源不存在结果
        
        :param message: 错误消息
        :return: 资源不存在结果对象
        """
        return Result.error(message=message, code=404).to_json()

    @staticmethod
    def bad_request(message: str = "请求参数错误") -> 'Result':
        """
        创建请求参数错误结果
        
        :param message: 错误消息
        :return: 请求参数错误结果对象
        """
        return Result.error(message=message, code=400).to_json()

    @staticmethod
    def business_error(message: str = "业务处理失败", code: int = 400, data: Any = None) -> 'Result':
        """
        创建业务逻辑错误结果
        
        :param message: 错误消息
        :param code: HTTP状态码
        :param data: 返回数据
        :return: 业务逻辑错误结果对象
        """
        return Result(status=False, code=code, data=data, message=message).to_json()

    @staticmethod
    def paginated(data: Any = None, total: int = 0, page: int = 1, per_page: int = 10, 
                  message: str = "操作成功") -> 'Result':
        """
        创建分页结果
        
        :param data: 返回数据列表
        :param total: 总记录数
        :param page: 当前页码
        :param per_page: 每页记录数
        :param message: 成功消息
        :return: 分页结果对象
        """
        paginated_data = {
            "items": data if data is not None else [],
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": (total + per_page - 1) // per_page if per_page > 0 else 0
            }
        }
        return Result.success(data=paginated_data, message=message)