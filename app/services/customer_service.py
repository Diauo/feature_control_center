from app import db
from sqlalchemy import text, func
from app.models.base_models import Feature, Category, Customer
from app.util.serviceUtil import model_to_dict
def get_all_customer():
    result = Customer.query.all()
    return True, "成功", result

def get_customer_by_id(customer_id):
    if not customer_id:
        return False, "customer_id为空", []
    result = Customer.query.filter_by(id = customer_id)
    return True, "成功", result