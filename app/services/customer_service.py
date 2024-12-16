from app import db
from sqlalchemy import text
from app.models.base_models import Customer
from app.util.serviceUtil import model_to_dict

def get_all_customer():
    sql = text('''
        SELECT * FROM BASE_CUSTOMER
    ''')
    result = db.session.execute(sql).fetchall()
    return True, "成功", model_to_dict(result)

def get_customer_by_id(customer_id):
    if not customer_id:
        return False, "customer_id为空", []
    sql = text('''
        SELECT * FROM BASE_CUSTOMER WHERE ID = :customer_id
    ''')
    result = db.session.execute(sql, {'customer_id':customer_id}).fetchall()
    return True, "成功", model_to_dict(result)