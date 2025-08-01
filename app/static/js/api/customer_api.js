import api from './api.js';

const customer_api = {
  get_all_customer() {
    return api.client.get('/cust/get_all_customer');
  }
};

export default customer_api