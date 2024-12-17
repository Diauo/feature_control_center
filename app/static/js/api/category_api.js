const category_api = {
  get_all_category() {
    return axios.get('/cate/get_all_category');
  },
  get_category_by_customer_id(customer_id) {
    return axios.get('/cate/get_category_by_customer_id?customer_id=' + customer_id);
  }
};

export default category_api