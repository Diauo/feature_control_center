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

def create_default_customer():
    """
    检查并创建默认客户
    客户名: GREY.ECHO.UNIT
    """
    # 检查是否已存在默认客户
    default_customer = db.session.query(Customer).filter_by(name='GREY.ECHO.UNIT').first()
    
    if default_customer:
        # 默认客户已存在
        return default_customer
    else:
        # 创建默认客户
        default_customer = Customer(
            name='GREY.ECHO.UNIT',
            description='默认客户账户'
        )
        
        try:
            db.session.add(default_customer)
            db.session.commit()
            return default_customer
        except Exception as e:
            db.session.rollback()
            raise
