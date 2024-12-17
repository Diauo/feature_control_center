from app import db
from sqlalchemy import text
from app.models.base_models import Category
from app.util.serviceUtil import model_to_dict

def get_category_by_customer_id(customer_id = None):
    condition = ""
    if customer_id:
        condition = "WHERE CG.ID = :customer_id";
    sql = text(f'''
                select cg.*, group_concat(tg.name, ',') tags from base_category cg
                left join union_category_tag uct on cg.id = uct.category_id
                left join base_tag tg on tg.id = uct.tag_id
                {condition}
                group by cg.id
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    categorys = model_to_dict(result, Category)
    # 添加折叠关系和选中关系
    for item in categorys:
        item['expanded'] = False
        item['selected'] = False
    # 将数据转换为字典格式，便于查找
    data_dict = {item['id']: item for item in categorys}
    # 构建父子关系
    for item in categorys:
        parent_id = item.get('parent_id')
        if parent_id == 0:
            continue;
        if parent_id is not None and data_dict.get(parent_id) is not None:
            if data_dict[parent_id].get('child') is not None:
                data_dict[parent_id].get('child').append(item)
            else:
                data_dict[parent_id]['child'] = [item]
    # 提取顶层节点
    category_tree = [item for item in categorys if item['parent_id'] == 0]
    return True, "成功", category_tree
