from app import db
from sqlalchemy import text, func
from app.models.base_models import Feature, Category, Customer
from app.util.serviceUtil import model_to_dict
def get_all_feature():
    sql = text('''
               SELECT FT.ID, FT.NAME, FT.DESCRIPTION, FT.CUSTOMER_ID,
                    GROUP_CONCAT(CG.NAME, ',') category_tags,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_CATEGORY UFC ON FT.ID = UFC.FEATURE_ID
                LEFT JOIN BASE_CATEGORY CG ON UFC.CATEGORY_ID = CG.ID
                LEFT JOIN BASE_CUSTOMER CT ON FT.CUSTOMER_ID = CT.ID
                GROUP BY FT.ID, CT.ID
               ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_customer_id(customer_id):
    if not customer_id:
        return False, "客户ID[customer_id]为空", []
    sql = text('''
               SELECT FT.ID, FT.NAME, FT.DESCRIPTION, FT.CUSTOMER_ID,
                    GROUP_CONCAT(CG.NAME, ',') category_tags,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_CATEGORY UFC ON FT.ID = UFC.FEATURE_ID
                LEFT JOIN BASE_CATEGORY CG ON UFC.CATEGORY_ID = CG.ID
                LEFT JOIN BASE_CUSTOMER CT ON FT.CUSTOMER_ID = CT.ID
                WHERE CT.ID = :customer_id
                GROUP BY FT.ID, CT.ID
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_category_tags_id(category_id = None, tags = None):
    if not category_id and not tags:
        return False, "没有有效参数分类ID[category_id]和标签ID[tags]", []
    condition = "WHERE "
    tags_string = ""
    if category_id:
        condition += " CG.ID = :category_id AND"
    if tags:
        tags_string = ",".join(tags)
        condition += " TG.ID in (:tags)"
    # 移除多余字符
    if condition.endswith("AND"):
        condition = condition[:-3]
    per_sql = f'''
               SELECT FT.ID, FT.NAME, FT.DESCRIPTION, FT.CUSTOMER_ID,
                    GROUP_CONCAT(CG.NAME, ',') category_tags,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_CATEGORY UFC ON FT.ID = UFC.FEATURE_ID
                LEFT JOIN BASE_CATEGORY CG ON UFC.CATEGORY_ID = CG.ID
                LEFT JOIN union_feature_tag UFT ON FT.ID = UFT.FEATURE_ID
                LEFT JOIN BASE_tag TG ON UFT.tag_ID = TG.ID
                LEFT JOIN BASE_CUSTOMER CT ON FT.CUSTOMER_ID = CT.ID
                {condition}
                GROUP BY FT.ID, CT.ID
               '''
    sql = text(per_sql)
    result = db.session.execute(sql, {'category_id': category_id, 'tags': tags_string}).fetchall()
    return True, "成功", model_to_dict(result, Feature)