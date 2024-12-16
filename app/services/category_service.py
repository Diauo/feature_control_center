from app import db
from sqlalchemy import text
from app.models.base_models import Category
from app.util.serviceUtil import model_to_dict

def get_category_by_customer_id(customer_id):
    sql = text('''
                SELECT CG.*, GROUP_CONCAT(TG.NAME, ',') TAGS FROM BASE_CATEGORY CG
                LEFT JOIN UNION_CATEGORY_TAG UCT ON CG.ID = UCT.CATEGORY_ID
                LEFT JOIN BASE_TAG TG ON TG.ID = UCT.TAG_ID
                WHERE CG.ID = :customer_id
                GROUP BY CG.ID
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    categorys = model_to_dict(result, Category)
    # 将数据转换为字典格式，便于查找
    data_dict = {item['id']: item for item in categorys}
    # 初始化每个字典中的child键
    for item in categorys:
        item['child'] = []
    # 构建父子关系
    for item in categorys:
        parent_id = item['parent_id']
        if parent_id is not None:
            data_dict[parent_id]['child'].append(item)
    # 提取顶层节点
    category_tree = [item for item in categorys if item['parent_id'] is None]
    return True, "成功", category_tree
