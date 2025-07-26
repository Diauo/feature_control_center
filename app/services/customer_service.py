from app import db
from sqlalchemy import text
from app.models.base_models import Customer
from app.util.serviceUtil import model_to_dict

def get_all_customer():
    sql = text('''
        select * from base_customer
    ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result, Customer)

def get_customer_by_id(customer_id):
    if customer_id is None:
        return False, "customer_id为空", []
    sql = text('''
        select * from base_customer where id = :customer_id
    ''')
    result = db.session.execute(sql, {'customer_id':customer_id}).fetchall()
    return True, "成功", model_to_dict(result, Customer)

def get_customer_by_name(customer_name):
    if customer_name is None:
        return False, "customer_name为空", []
    sql = text('''
        select * from base_customer where name = :customer_name
    ''')
    result = db.session.execute(sql, {'customer_name':customer_name}).fetchall()
    return True, "成功", model_to_dict(result, Customer)
