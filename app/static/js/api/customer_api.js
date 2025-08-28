import api from './api.js';

const customer_api = {
  // 获取所有客户（管理员）
  get_all_customer() {
    return api.client.post('/cust/get_customers');
  },
  
  // 获取客户（操作员）
  get_customers_by_customer_id(customer_id) {
    return api.client.post('/cust/get_customers_by_customer_id', { customer_id: customer_id });
  },
  
  // 新增客户（管理员）
  add_customer(customer) {
    return api.client.post('/cust/add_customer', customer);
  },
  
  // 删除客户（管理员）
  del_customer(customer_id) {
    return api.client.post('/cust/del_customer', { id: customer_id });
  },
  
  // 更新客户（管理员）
  update_customer(customer) {
    return api.client.post('/cust/update_customer', customer);
  }
};

export default customer_api;