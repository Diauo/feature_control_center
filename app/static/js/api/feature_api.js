const feature_api = {
  get_all_feature() {
    return axios.get('/feat/get_all_feature');
  },
  get_feature_by_customer_id(id) {
    return axios.get('/feat/get_feature_by_customer_id?customer_id=' + id);
  }
};

export default feature_api