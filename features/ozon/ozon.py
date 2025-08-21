from . import ME3
import requests
import json
from datetime import datetime
import urllib.parse


class OzonAPI:
    def __init__(self, configs):
        """
        初始化OzonAPI类
        :param configs: 配置字典
        """
        self.apiKey = configs.get('OZON_api_key')
        self.clientId = str(configs.get('OZON_client_id'))
        
        if not self.apiKey:
            raise ValueError("配置中未定义ozon的api-key！")
        if not self.clientId:
            raise ValueError("配置中未定义ozon的client-id！")
        
        self.headers = {
            'Content-Type': 'application/json',
            'api-key': self.apiKey,
            'client-id': self.clientId
        }
        
        self.item_list_url = configs.get("item_list_url")
        self.item_info_url = configs.get("item_info_url")
        self.stocks_by_warehouse_url = configs.get("stocks_by_warehouse_url")
        self.stocks_update_url = configs.get("stocks_update_url")

    # 查询有条形码的商品
    def get_item_list(self, last_id="", limit=10):
        request_body = {
            "filter": {
                "visibility": "ALL"
            },
            "cursor": last_id,
            "limit": limit
        }
        try:
            response = requests.post(
                self.item_list_url, json=request_body, headers=self.headers)
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            log_msg = f"查询有条形码的商品异常： {err_msg}，last_id：{last_id}"
            return False, log_msg, None, None, None
        if response.status_code != 200:
            return False, f"查询有条形码的商品请求失败：{response.status_code}，last_id：{last_id}", None, None, None
        result = json.loads(response.text)
        return True, f"成功", result.get("total"), result.get("cursor"), result.get("items")

    # 查询商品具体的条形码和sku
    def get_item_barcode_and_sku(self, product_id_list):
        request_body = {
            "product_id": product_id_list
        }
        try:
            response = requests.post(
                self.item_info_url, json=request_body, headers=self.headers)
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            log_msg = f"查询商品具体的条形码和sku异常： {err_msg}"
            return False, log_msg, None
        if response.status_code != 200:
            return False, f"查询商品具体的条形码和sku，请求失败：{response.status_code}", None
        result = json.loads(response.text).get("items")
        return True, f"成功", result

    # 查询sku对应的库存信息
    def get_item_inventory_info(self, skus):
        request_body = {
            "sku": skus
        }
        try:
            response = requests.post(
                self.stocks_by_warehouse_url, json=request_body, headers=self.headers)
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            skus_str = ", ".join(skus)
            log_msg = f"查询sku对应的库存信息 ： {err_msg}。本批次sku：{skus_str}"
            return False, log_msg, None
        if response.status_code != 200:
            skus_str = ", ".join(skus)
            return False, f"查询sku对应的库存信息请求失败：{response.status_code}。本批次sku：{skus_str}", None
        result = json.loads(response.text).get("result")
        return True, "成功", result

    # 批量更新库存商品的数量
    def update_item_inventory(self, update_stocks_data_list):
        try:
            request_body = {
                "stocks": update_stocks_data_list
            }
            response = requests.post(
                self.stocks_update_url, json=request_body, headers=self.headers)
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            log_msg = f"批量更新库存商品的数量异常： {err_msg}"
            return False, log_msg, None
        if response.status_code != 200:
            return False, f"批量更新库存商品的数量请求失败：{response.status_code}", None
        result = json.loads(response.text).get("result")
        return True, "成功", result

    # 获取商品的ME3库存信息
    def get_ME3_inventory_info(self, url, sku, store_code, key, secret):
        request_params = {
            "pageNo": "1",
            "pageSize": "5",
            "startModifiedTime": "1970-01-01 00:00:01",
            "endModifiedTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "barcode": sku,
            "store_code": store_code,
        }
        # 组装完整请求参数
        request_params_string = ME3.assembly_request_body(
            "stock.goods_sscx", key, secret, request_params
        )
        encoded_params = urllib.parse.urlencode(request_params_string)
        full_url = f"{url}&{encoded_params}"
        try:
            response = requests.get(full_url, verify=False)
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            log_msg = f"查询ME3库存信息异常： {err_msg}"
            return False, log_msg, None
        ME3_result = json.loads(response.text)
        # 检查ME3返回结果，获取商品库存
        if "status" in ME3_result and ME3_result["status"] == 1:
            # 没有商品数据
            if not ('data' in ME3_result and 'data' in ME3_result["data"]):
                log_msg = f"ME3店铺{store_code}中没有{sku}的商品数据；请求地址：\n\t\t{full_url}"
                return False, log_msg, None
            shop_stock = ME3_result["data"]["data"]
            if len(shop_stock) != 0:
                quantity = shop_stock[0]["num"]
                return True, f"成功", quantity
            else:
                return False, f"没有有效商品数据", None
        else:
            msg = ME3_result.get("message")
            return False, f"请求ME3获取商品库存失败，ME3消息：{msg}", None
