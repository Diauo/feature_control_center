import api from './api.js';

const feature_api = {
  // 获取所有功能（管理员）
  get_all_feature() {
    return api.client.post('/feat/get_features');
  },
  
  // 获取功能（操作员）
  get_feature_by_customer_id(customer_id) {
    return api.client.post('/feat/get_features_by_customer_id', { customer_id: customer_id });
  },
  
  // 根据分类获取功能
  get_feature_by_category_id(category_id, customer_id = null) {
    const data = { category_id: category_id };
    if (customer_id !== null) {
      data.customer_id = customer_id;
    }
    return api.client.post('/feat/get_feature_by_category_id', data);
  },
  
  // 执行功能
  execute_feature(id, clientId) {
    return api.client.post('/feat/execute', {"feature_id": id, "client_id": clientId });
  },
  
  // 注册功能
  register_feature(formData) {
    return api.client.post('/feat/register', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
  },
  
  // 删除功能（管理员）
  delete_feature(feature_id) {
    return api.client.post('/feat/del_feature', { id: feature_id });
  },
  
  // 新增功能（管理员）
  add_feature(feature) {
    return api.client.post('/feat/add_feature', feature);
  },
  
  // 更新功能（管理员）
  update_feature(feature) {
    return api.client.post('/feat/update_feature', feature);
  }
};

export default feature_api;