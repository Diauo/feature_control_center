const customer_api = {
  get_all_customer() {
    return axios.get('/cust/get_all_customer');
  }
};

export default customer_api