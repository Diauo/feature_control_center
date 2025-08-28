import api from './api.js';

const category_api = {
  // 获取所有分类（管理员）
  get_all_category() {
    return api.client.post('/cate/get_categories');
  },
  
  // 获取分类（操作员）
  get_categories_by_customer_id(customer_id) {
    return api.client.post('/cate/get_categories_by_customer_id', { customer_id: customer_id });
  },
  
  // 新增分类（管理员）
  add_category(category) {
    return api.client.post('/cate/add_category', category);
  },
  
  // 删除分类（管理员）
  del_category(category_id) {
    return api.client.post('/cate/del_category', { id: category_id });
  },
  
  // 更新分类（管理员）
  update_category(category) {
    return api.client.post('/cate/update_category', category);
  }
};

export default category_api;
