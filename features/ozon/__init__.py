__meta__ = {
    "name": "OZON库存同步",
    "description": "执行OZON库存同步",
    "customer": "GREY.ECHO.UNIT",
    "configs": {
        "ME3_url": (None, "ME3网店库存获取地址"),
        "ME3_app_key": (None, "ME3分配的授权key"),
        "ME3_secret": (None, "ME3分配的授权秘钥"),
        "OZON_api_key": (None, "ozon api Key"),
        "OZON_client_id": (None, "ozon clientId"),
        "limit_Warehouse_id": (None, "ME3限定仓库编码"),
        "data_source_file_path": (None, "数据源文件全路径"),
        "item_list_url": ("https://api-seller.ozon.ru/v4/product/info/stocks", "OZON查询物品列表API"),
        "item_info_url": ("https://api-seller.ozon.ru/v3/product/info/list", "OZON查询商品详细信息API"),
        "stocks_by_warehouse_url": ("https://api-seller.ozon.ru/v1/product/info/stocks-by-warehouse/fbs", "OZON查询商品库存API"),
        "stocks_update_url": ("https://api-seller.ozon.ru/v2/products/stocks", "OZON更新库存API")
    }
}

import os
import traceback
import time
import pandas as pd
from app.util.feature_execution_context import FeatureExecutionContext
from .ozon import OzonAPI

# 初始化

def run(configs: dict, ctx: FeatureExecutionContext):
    """
    模块的主执行函数
    :param configs: 配置字典
    :param ctx: 执行上下文
    :return: (bool, str, dict) 是否成功，提示信息，返回数据
    """
    # 创建OzonAPI实例
    ozon_api = OzonAPI(configs)

    url = configs.get("ME3_url")
    key = configs.get("ME3_app_key")
    secret = configs.get("ME3_secret")
    limit_warehouse_id = configs.get("limit_Warehouse_id")
    data_source_file_path = configs.get("data_source_file_path")


    ctx.log("开始执行ozon库存同步")
    continue_run = True
    last_id = ""
    # 当前SKU最终更新的库存数量
    updated_count_dict = {}
    # 读取同步控制数据源
    need_sync_sku = {}
    if data_source_file_path:
        if not os.path.exists(data_source_file_path):
            log_msg = f"未找到同步控制数据源文件：{data_source_file_path}"
            ctx.error(log_msg)
            return False, log_msg, None
        else:
            itemData = pd.read_excel(data_source_file_path, header=0, dtype={"sku": str, "store_code": str})
            for row in itemData.itertuples(index=False):
                if not row.sku:
                    ctx.log("没有读取到有效的sku，跳过")
                    continue
                if not row.store_code :
                    ctx.log("没有读取到有效的仓库代码，跳过")
                    continue
                need_sync_sku[str(row.sku).strip()]=str(row.store_code).strip()
    # 上次更新结束时间戳
    last_end_time = 0
    while continue_run:
        try:
            sku_mapping_dict = {}
            id_sku_mapping_dict = {}
            continue_run = False
            # 查询一批商品信息
            status, message, total, last_id, item_list = ozon_api.get_item_list(last_id, 100)
            if not status:
                ctx.error(message)
                break
            # 检查是否还有更多数据
            if last_id:
                continue_run = True
            elif not last_id and len(item_list) == 0:
                # 无数据，退出
                break
            log_msg = f"下一同步批次:{last_id}"
            ctx.log(log_msg)
            # 组装product_id用于查询sku和条形码
            product_id_list = []
            for item in item_list:
                # 查询商品具体的条形码和sku
                product_id = item.get("product_id")
                product_id_list.append(product_id)
            status, message, item_list = ozon_api.get_item_barcode_and_sku(product_id_list)
            if not status:
                ctx.error(message)
                continue
            # 组装sku列表用于查询库存状态
            skus = []
            for item in item_list:
                try:
                    sku = item.get("sources")[0].get("sku")
                    me3_sku = item.get("barcodes")[0]
                except Exception as e1:
                    offer_id = item.get("offer_id")
                    message = f"offer_id:{offer_id}数据不全，跳过："
                    ctx.error(message)
                    continue
                if not me3_sku:
                    continue
                # 检查这个sku是否存在于需要更新的sku中
                if not need_sync_sku.get(me3_sku):
                    continue
                product_id = item.get("id")
                id_sku_mapping_dict[product_id] = me3_sku
                sku_mapping_dict[sku] = me3_sku
                skus.append(sku)
            # 本批次没有有效数据，跳过
            if len(skus) == 0:
                message = "本批次没有有效数据，跳过"
                ctx.error(message)
                continue
            # 查询一批sku对应的库存信息
            status, message, item_stocks_list = ozon_api.get_item_inventory_info(skus)
            if not status:
                ctx.error(message)
                continue
            # 更新库存可以批量更新，但是30秒只能更新一次。这里组装最后更新库存的完整数据对象
            update_stocks_data_list = []
            for item in item_stocks_list:
                warehouse_id = item.get("warehouse_id")
                # 只同步仓库2的数据 1020001626927000
                if warehouse_id != limit_warehouse_id:
                    continue
                product_id = item.get("product_id")
                present = item.get("present")
                sku = item.get("sku")
                me3_sku = sku_mapping_dict[sku]
                store_codes = need_sync_sku.get(me3_sku)
                total_ME3_inventory = 0
                # 获取所有ME3仓库的数量并累加
                for store_code in store_codes.split(','):
                    # 获取商品的ME3库存信息
                    status, message, ME3_inventory = ozon_api.get_ME3_inventory_info(
                        url, me3_sku, store_code, key, secret)
                    if not status:
                        log_msg = f"{me3_sku}：{message}"
                        ctx.error(message)
                        continue
                    total_ME3_inventory += int(ME3_inventory)
                # 如果库存数量未变动，直接跳过
                if total_ME3_inventory == present:
                    log_msg = f"{me3_sku}：无需更新，库存数量未变动"
                    ctx.log(log_msg)
                    continue
                updated_count_dict[me3_sku] = total_ME3_inventory
                update_stocks_data_list.append({
                    "product_id": product_id,
                    "stock": ME3_inventory,
                    "warehouse_id": warehouse_id
                })
            # 当前时间戳，检查距离上次完成更新是否大于30秒
            if len(update_stocks_data_list) == 0:
                log_msg = f"当前同步批次{last_id}：没有需要更新的数据，跳过"
                ctx.error(log_msg)
                continue;
            current_time = time.time()
            elapsed_time =  current_time - last_end_time
            if elapsed_time < 30:
                # 如果未满足30秒，则休眠到满足条件再更新
                time.sleep(30 - elapsed_time)
            # 批量更新库存
            status, message, update_result = ozon_api.update_item_inventory(update_stocks_data_list)
            if not status:
                ctx.error(message)
                continue
            for result in update_result:
                product_id = result.get("product_id")
                updated = result.get("updated")
                update_msg = "成功" if updated else "失败"
                me3_sku = id_sku_mapping_dict[product_id]
                updated_count = updated_count_dict.get(me3_sku)
                log_msg = f"{me3_sku}: 更新{update_msg}，更新数量：{updated_count}"
                ctx.log(log_msg)
            # 计算休眠时间
            last_end_time = time.time()
        except Exception as e:
            err_msg = f"{type(e).__name__}：{e}"
            tb = traceback.format_exc()
            log_msg = f"{sku}：更新失败，错误：{err_msg}，\n{tb}"
            ctx.error(log_msg)
    ctx.log("Ozon库存同步执行完成")
    return True, "Ozon库存同步执行完成", None
