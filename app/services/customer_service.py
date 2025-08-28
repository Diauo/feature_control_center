from app import db
from sqlalchemy import text
from app.models.base_models import Customer
from app.models.user_models import UserCustomer
from app.util.serviceUtil import model_to_dict

def get_all_customer(user_id, role):
    """
    根据用户角色返回客户列表
    :param user_id: 当前用户ID
    :param role: 当前用户角色
    """
    try:
        if role == 'admin':
            # 管理员返回所有客户
            customers = db.session.query(Customer).all()
        else:
            # 操作员只返回自己关联的客户
            customer_ids = db.session.query(UserCustomer.customer_id).filter_by(user_id=user_id).all()
            customer_ids = [cid[0] for cid in customer_ids]
            if not customer_ids:
                return True, "无关联客户", []
            customers = db.session.query(Customer).filter(Customer.id.in_(customer_ids)).all()
        return True, "成功", [c.to_dict() for c in customers]
    except Exception as e:
        return False, f"查询失败: {str(e)}", []

def get_customer_by_name(customer_name):
    if customer_name is None:
        return False, "customer_name为空", []
    sql = text('''
        select * from base_customer where name = :customer_name
    ''')
    result = db.session.execute(sql, {'customer_name':customer_name}).fetchall()
    return True, "成功", model_to_dict(result, Customer)

def add_customer(customer_data):
    """
    添加新客户
    :param customer_data: 客户数据字典
    :return: (bool, str, dict) 是否成功，提示信息，添加后的数据
    """
    try:
        customer = Customer(
            name=customer_data.get('name'),
            description=customer_data.get('description')
        )
        db.session.add(customer)
        db.session.commit()
        return True, "添加成功", customer.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"添加失败: {str(e)}", None

def del_customer(customer_id):
    """
    删除指定ID的客户
    :param customer_id: 客户ID
    :return: (bool, str) 是否成功，提示信息
    """
    try:
        customer = Customer.query.get(customer_id)
        if not customer:
            return False, f"未找到ID为[{customer_id}]的客户"
        
        db.session.delete(customer)
        db.session.commit()
        return True, "删除成功"
    except Exception as e:
        db.session.rollback()
        return False, f"删除失败: {str(e)}"

def update_customer(customer_id, customer_data):
    """
    更新指定ID的客户
    :param customer_id: 客户ID
    :param customer_data: 客户数据字典
    :return: (bool, str, dict) 是否成功，提示信息，更新后的数据
    """
    try:
        customer = Customer.query.get(customer_id)
        if not customer:
            return False, f"未找到ID为[{customer_id}]的客户", None
        
        # 更新字段
        if 'name' in customer_data:
            customer.name = customer_data['name']
        if 'description' in customer_data:
            customer.description = customer_data['description']
            
        db.session.commit()
        return True, "更新成功", customer.to_dict()
    except Exception as e:
        db.session.rollback()
        return False, f"更新失败: {str(e)}", None

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
