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

def add_category_service(category_data):
    """
    添加新分类服务
    :param category_data: 分类数据字典
    :return: (bool, str, dict) 是否成功，提示信息，添加后的数据
    """
    try:
        category = Category(
            name=category_data.get('name'),
            parent_id=category_data.get('parent_id'),
            customer_id=category_data.get('customer_id'),
            description=category_data.get('description'),
            order_id=category_data.get('order_id'),
            depth_level=category_data.get('depth_level')
        )
        db.session.add(category)
        db.session.commit()
        return True, "添加成功", category.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"添加失败: {str(e)}", None

def update_category_service(category_id, category_data):
    """
    更新指定ID的分类服务
    :param category_id: 分类ID
    :param category_data: 分类数据字典
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    try:
        category = Category.query.get(category_id)
        if not category:
            return False, f"未找到ID为[{category_id}]的分类", None
        
        # 更新字段
        if 'name' in category_data:
            category.name = category_data['name']
        if 'parent_id' in category_data:
            category.parent_id = category_data['parent_id']
        if 'customer_id' in category_data:
            category.customer_id = category_data['customer_id']
        if 'description' in category_data:
            category.description = category_data['description']
        if 'order_id' in category_data:
            category.order_id = category_data['order_id']
        if 'depth_level' in category_data:
            category.depth_level = category_data['depth_level']
            
        db.session.commit()
        return True, "更新成功", category.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"更新失败: {str(e)}", None

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