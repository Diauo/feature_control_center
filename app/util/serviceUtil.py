
def model_to_dict(result, clazz):
    """
    将SQLAlchemy查询结果转换为字典列表
    :param result: SQLAlchemy查询结果
    """
    data_list = [clazz(**row._asdict()) for row in result]
    data_list_dict = [data.__dict__ for data in data_list]
    for data in data_list_dict:
        data.pop('_sa_instance_state', None)
    return data_list_dict