import api from './api.js';

const category_api = {
  get_all_category() {
    return api.client.get('/cate/get_all_category');
  },
  get_category_by_customer_id(customer_id) {
    return api.client.get('/cate/get_category_by_customer_id?customer_id=' + customer_id);
  },
  add_category(category) {
    return api.client.post('/cate/add_category', category);
  },
  del_category(category) {
    return api.client.post('/cate/del_category', category);
  },
};

export default category_api
