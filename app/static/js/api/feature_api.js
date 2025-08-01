import api from './api.js';

const feature_api = {
  get_all_feature() {
    return api.client.get('/feat/get_all_feature');
  },
  get_feature_by_customer_id(id) {
    return api.client.get('/feat/get_feature_by_customer_id?customer_id=' + id);
  },
  execute_feature(id, clientId) {
    return api.client.post('/feat/execute', {"feature_id": id, "client_id": clientId });
  }
};

export default feature_api