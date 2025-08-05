import api from './api.js';

const user_api = {
  /**
   * 用户登录
   * @param {Object} credentials - 登录凭据 {username, password}
   * @returns {Promise}
   */
  login(credentials) {
    return api.client.post('/users/login', credentials);
  },

  /**
   * 用户注册
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  register(userData) {
    return api.client.post('/users/register', userData);
  },

  /**
   * 用户登出
   * @returns {Promise}
   */
  logout() {
    return api.client.post('/users/logout');
  },

  /**
   * 刷新访问令牌
   * @param {string} refreshToken - 刷新令牌
   * @returns {Promise}
   */
  refreshTokens(refreshToken) {
    return api.client.post('/users/refresh', { refresh_token: refreshToken });
  },

  /**
   * 获取当前用户信息
   * @returns {Promise}
   */
  getCurrentUser() {
    return api.client.get('/users/me');
  },

  /**
   * 获取当前用户关联的客户
   * @returns {Promise}
   */
  getMyCustomers() {
    // 这个API需要在后端实现
    // 暂时返回一个模拟的实现
    return api.client.get('/users/me/customers');
  },

  /**
   * 获取用户列表（仅管理员）
   * @param {Object} params - 查询参数
   * @returns {Promise}
   */
  getUsers(params) {
    return api.client.get('/users/list', { params });
  },

  /**
   * 获取用户详情（仅管理员）
   * @param {number} userId - 用户ID
   * @returns {Promise}
   */
  getUser(userId) {
    return api.client.get(`/users/${userId}`);
  },

  /**
   * 创建用户（仅管理员）
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  createUser(userData) {
    return api.client.post('/users/', userData);
  },

  /**
   * 更新用户（仅管理员）
   * @param {number} userId - 用户ID
   * @param {Object} userData - 用户数据
   * @returns {Promise}
   */
  updateUser(userId, userData) {
    return api.client.put(`/users/${userId}`, userData);
  },

  /**
   * 删除用户（仅管理员）
   * @param {number} userId - 用户ID
   * @returns {Promise}
   */
  deleteUser(userId) {
    return api.client.delete(`/users/${userId}`);
  }
};

export default user_api;