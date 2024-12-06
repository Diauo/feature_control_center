from app import db
from sqlalchemy import text, func
from app.models.base_models import Feature, Category, Customer
from app.util.serviceUtil import model_to_dict
def get_all_feature():
    # 查询功能
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
        return False, "customer_id为空", []
    # 查询功能
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

def get_feature_by_category_tags_id(category_tags):
    # 查询功能
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