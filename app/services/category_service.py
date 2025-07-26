from app import db
from sqlalchemy import text
from app.models.base_models import Category
from app.util.serviceUtil import model_to_dict

def get_category_by_customer_id(customer_id = None):
    condition = ""
    if not customer_id is None:
        condition = "WHERE CG.ID = :customer_id";
    sql = text(f'''
                select cg.* from base_category cg
                {condition}
                group by cg.id
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    categorys = model_to_dict(result, Category)
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

def add_category(category):
    # 查找标签对应的ID，并插入关联关系
    
    # 没有设定排序ID，自动排序

    pass;

def del_category(category_id):
    sql = text('''select count(id) child_count from base_category where parent_id = :category_id''')
    result = db.session.execute(sql, {'category_id': category_id})
    row = result.fetchone()
    child_count = row.child_count  
    # 如果有子级数据，阻止删除
    if child_count > 0:
        return False, f"该分类仍有{child_count}个子分类，请删除子分类再删除本分类！", None
    sql = text('''delete from base_category where id = :category_id''')
    result = db.session.execute(sql, {'category_id': category_id})
    row_count = result.rowcount
    db.session.commit()
    return True, f"成功删除{row_count}条数据", None

def get_category_by_name(category_name = None):
    if category_name is None:
        return False, "category_name为空", []
    sql = text('''
        select * from base_category where name = :category_name
    ''')
    result = db.session.execute(sql, {'category_name': category_name}).fetchall()
    return True, "成功", model_to_dict(result, Category)