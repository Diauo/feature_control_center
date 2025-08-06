import api from './api.js';

const config_api = {
  // 获取所有配置
  get_all_config() {
    return api.client.get('/config/get_all_config');
  },
  
  // 新增配置
  add_config(config) {
    return api.client.post('/config/add_config', config);
  },
  
  // 更新配置
  update_config(config_id, config) {
    return api.client.put(`/config/update_config/${config_id}`, config);
  },
  
  // 删除配置
  delete_config(config_id) {
    return api.client.delete(`/config/delete_config/${config_id}`);
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