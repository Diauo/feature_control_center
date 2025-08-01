import axios from 'axios';

export default {
  /**
   * 用户登录
   * @param {Object} credentials - 登录凭据 {username, password}
   * @returns {Promise}
   */
  login(credentials) {
    return axios.post('/api/users/login', credentials);
  },

  /**
   * 用户注册
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  register(userData) {
    return axios.post('/api/users/register', userData);
  },

  /**
   * 用户登出
   * @returns {Promise}
   */
  logout() {
    return axios.post('/api/users/logout');
  },

  /**
   * 刷新访问令牌
   * @param {string} refreshToken - 刷新令牌
   * @returns {Promise}
   */
  refreshTokens(refreshToken) {
    return axios.post('/api/users/refresh', { refresh_token: refreshToken });
  },

  /**
   * 获取当前用户信息
   * @returns {Promise}
   */
  getCurrentUser() {
    return axios.get('/api/users/me');
  },

  /**
   * 获取当前用户关联的客户
   * @returns {Promise}
   */
  getMyCustomers() {
    // 这个API需要在后端实现
    // 暂时返回一个模拟的实现
    return axios.get('/api/users/me/customers');
  },

  /**
   * 获取用户列表（仅管理员）
   * @param {Object} params - 查询参数
   * @returns {Promise}
   */
  getUsers(params) {
    return axios.get('/api/users/list', { params });
  },

  /**
   * 获取用户详情（仅管理员）
   * @param {number} userId - 用户ID
   * @returns {Promise}
   */
  getUser(userId) {
    return axios.get(`/api/users/${userId}`);
  },

  /**
   * 创建用户（仅管理员）
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  createUser(userData) {
    return axios.post('/api/users/', userData);
  },

  /**
   * 更新用户（仅管理员）
   * @param {number} userId - 用户ID
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  updateUser(userId, userData) {
    return axios.put(`/api/users/${userId}`, userData);
  },

  /**
   * 删除用户（仅管理员）
   * @param {number} userId - 用户ID
   * @returns {Promise}
   */
  deleteUser(userId) {
    return axios.delete(`/api/users/${userId}`);
  }
};