from app import db
from sqlalchemy import text
from app.models.base_models import Feature
from app.util.serviceUtil import model_to_dict

def get_all_feature():
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_customer_id(customer_id):
    if customer_id is None:
        return False, "客户ID[customer_id]为空", []
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                where ct.id = :customer_id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_category_id(category_id):
    if category_id is None:
        return False, "分类ID[category_id]为空", []
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    ct.name customer_name from base_feature ft
                left join base_customer ct on ft.customer_id = ct.id
                where ft.category_id = :category_id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql, {'category_id': category_id}).fetchall()
    return True, "成功", model_to_dict(result, Feature)
def add_feature(feature):
    """
    添加新功能
    :param feature: Feature对象
    :return: (bool, str, dict) 是否成功，提示信息，添加后的数据
    """
    db.session.add(feature)
    db.session.commit()
    return True, "添加成功", feature.to_dict()

def update_feature(feature_id, name=None, description=None, customer_id=None, category_id=None):
    """
    更新指定feature_id的功能信息
    :param feature_id: 功能ID
    :param name: 功能名称
    :param description: 功能描述
    :param customer_id: 客户ID
    :param category_id: 分类ID
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    feature = Feature.query.get(feature_id)
    if not feature:
        return False, f"未找到ID为[{feature_id}]的功能", None
    if name is not None:
        feature.name = name
    if description is not None:
        feature.description = description
    if customer_id is not None:
        feature.customer_id = customer_id
    if category_id is not None:
        feature.category_id = category_id
    db.session.commit()
    return True, "更新成功", feature.to_dict()

def delete_feature(feature_id):
    """
    删除指定feature_id的功能
    :param feature_id: 功能ID
    :return: (bool, str) 是否成功，提示信息
    """
    feature = Feature.query.get(feature_id)
    if not feature:
        return False, f"未找到ID为[{feature_id}]的功能"
    db.session.delete(feature)
    db.session.commit()
    return True, "删除成功"