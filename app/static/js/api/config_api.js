import api from './api.js';

const config_api = {
  // 获取所有配置（管理员）
  get_all_config() {
    return api.client.post('/config/get_configs');
  },
  
  // 获取配置（操作员）
  get_configs_by_customer_id(customer_id) {
    return api.client.post('/config/get_configs_by_customer_id', { customer_id: customer_id });
  },
  
  // 获取筛选后的配置
  get_filtered_config(params) {
    return api.client.post('/config/get_filtered_configs', params);
  },
  
  // 新增配置（管理员）
  add_config(config) {
    return api.client.post('/config/add_config', config);
  },
  
  // 更新配置（管理员）
  update_config(config) {
    return api.client.post('/config/update_config', config);
  },
  
  // 删除配置（管理员）
  delete_config(config_id) {
    return api.client.post('/config/del_config', { id: config_id });
  },
  
  // 重载配置
  reload() {
    return api.client.post('/config/reload');
  },
  
  // 清理无效配置
  cleanup() {
    return api.client.post('/config/cleanup');
  }
};

export default config_api;