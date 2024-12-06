(() => {
    // 检测 axios 是否加载
    if (typeof axios === 'undefined') {
      throw new Error('Axios没有加载！');
    }
  
    // 封装 API 方法
    const api = {
      get_all_feature() {
        return axios.get('/feat/get_all_feature');
      },
      get_feature_by_customer_id(id) {
        return axios.get(`/feat/get_feature_by_customer_id/${id}`);
      }
    };
  
    // 将 API 模块暴露到全局
    window.api = api;
  })();