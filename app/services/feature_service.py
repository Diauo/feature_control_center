from app import db
from sqlalchemy import text
from app.models.base_models import Feature
from app.util.serviceUtil import model_to_dict
def get_all_feature():
    sql = text('''
               SELECT FT.ID, FT.NAME, FT.DESCRIPTION, FT.CUSTOMER_ID,
                    GROUP_CONCAT(TG.NAME, ',') tags,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_TAG UFT ON FT.ID = UFT.FEATURE_ID
                LEFT JOIN BASE_TAG TG ON UFT.TAG_ID = TG.ID
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
                    GROUP_CONCAT(TG.NAME, ',') TAGS,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_TAG UFT ON FT.ID = UFT.FEATURE_ID
                LEFT JOIN BASE_TAG TG ON UFT.TAG_ID = TG.ID
                LEFT JOIN BASE_CUSTOMER CT ON FT.CUSTOMER_ID = CT.ID
                WHERE CT.ID = :customer_id
                GROUP BY FT.ID, CT.ID
               ''')
    result = db.session.execute(sql, {'customer_id': customer_id}).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_tags_id(tags = None):
    if not tags:
        return False, "没有有效参数标签ID[tags]", []
    condition_list = []
    condition = ""
    tags_string = ""
    if tags:
        tags_string = ",".join(tags)
        condition_list.append("TG.ID in (:tags)")
    if len(condition_list)!=0:
        condition = "WHERE " + (" AND ".join(condition_list))
    per_sql = f'''
               SELECT FT.ID, FT.NAME, FT.DESCRIPTION, FT.CUSTOMER_ID,
                    GROUP_CONCAT(CG.NAME, ',') TAGS,
                    CT.name customer_name FROM BASE_FEATURE FT
                LEFT JOIN UNION_FEATURE_TAG UFT ON FT.ID = UFT.FEATURE_ID
                LEFT JOIN BASE_TAG TG ON UFT.TAG_ID = TG.ID
                LEFT JOIN BASE_CUSTOMER CT ON FT.CUSTOMER_ID = CT.ID
                {condition}
                GROUP BY FT.ID, CT.ID
               '''
    sql = text(per_sql)
    result = db.session.execute(sql, {'tags': tags_string}).fetchall()
    return True, "成功", model_to_dict(result, Feature)