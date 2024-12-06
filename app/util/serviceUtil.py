
def model_to_dict(result, clazz):
    data_list = [clazz(**row._asdict()) for row in result]
    data_list_dict = [data.__dict__ for data in data_list]
    for data in data_list_dict:
        data.pop('_sa_instance_state', None)
    return data_list_dict