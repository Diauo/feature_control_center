from app import db
from sqlalchemy import text
from app.models.base_models import Feature
from app.util.serviceUtil import model_to_dict
def get_all_feature():
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    group_concat(tg.name, ',') tags,
                    ct.name customer_name from base_feature ft
                left join union_feature_tag uft on ft.id = uft.feature_id
                left join base_tag tg on uft.tag_id = tg.id
                left join base_customer ct on ft.customer_id = ct.id
                group by ft.id, ct.id
               ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Feature)

def get_feature_by_customer_id(customer_id):
    if not customer_id:
        return False, "客户ID[customer_id]为空", []
    sql = text('''
               select ft.id, ft.name, ft.description, ft.customer_id,
                    group_concat(tg.name, ',') tags,
                    ct.name customer_name from base_feature ft
                left join union_feature_tag uft on ft.id = uft.feature_id
                left join base_tag tg on uft.tag_id = tg.id
                left join base_customer ct on ft.customer_id = ct.id
                where ct.id = :customer_id
                group by ft.id, ct.id
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
               select ft.id, ft.name, ft.description, ft.customer_id,
                    group_concat(cg.name, ',') tags,
                    ct.name customer_name from base_feature ft
                left join union_feature_tag uft on ft.id = uft.feature_id
                left join base_tag tg on uft.tag_id = tg.id
                left join base_customer ct on ft.customer_id = ct.id
                {condition}
                group by ft.id, ct.id
               '''
    sql = text(per_sql)
    result = db.session.execute(sql, {'tags': tags_string}).fetchall()
    return True, "成功", model_to_dict(result, Feature)