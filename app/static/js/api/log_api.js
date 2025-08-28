import api from './api.js';

const log_api = {
    /**
     * 查询日志（根据用户角色自动选择）
     * @param {Object} params - 查询参数
     * @returns {Promise}
     */
    query(params) {
        // 这个方法需要在调用时根据用户角色选择具体的实现
        // 在useLogs.js中会根据用户角色调用具体的API方法
        // 这里提供一个默认实现，实际使用时会被覆盖
        return api.client.post('/log/query', params);
    },
    
    /**
     * 查询日志（管理员）
     * @param {Object} params - 查询参数
     * @param {number} params.feature_id - 功能ID
     * @param {string} params.start_date - 开始日期
     * @param {string} params.end_date - 结束日期
     * @param {string} params.keyword - 关键字
     * @param {string} params.execution_type - 执行类型 (manual/scheduled)
     * @returns {Promise}
     */
    get_logs(params) {
        return api.client.post('/log/get_logs', params);
    },

    /**
     * 查询日志（操作员）
     * @param {Object} params - 查询参数
     * @param {number} params.customer_id - 客户ID
     * @param {number} params.feature_id - 功能ID
     * @param {string} params.start_date - 开始日期
     * @param {string} params.end_date - 结束日期
     * @param {string} params.keyword - 关键字
     * @param {string} params.execution_type - 执行类型 (manual/scheduled)
     * @returns {Promise}
     */
    get_logs_by_customer_id(params) {
        return api.client.post('/log/get_logs_by_customer_id', params);
    },

    /**
     * 获取日志明细内容
     * @param {number} id - 日志ID
     * @returns {Promise}
     */
    getLogDetails(id) {
        return api.client.post('/log/get_log_details', { id: id });
    },
    
    /**
     * 新增日志（管理员）
     * @param {Object} log - 日志数据
     * @returns {Promise}
     */
    add_log(log) {
        return api.client.post('/log/add_log', log);
    },
    
    /**
     * 删除日志（管理员）
     * @param {number} id - 日志ID
     * @returns {Promise}
     */
    del_log(id) {
        return api.client.post('/log/del_log', { id: id });
    },
    
    /**
     * 更新日志（管理员）
     * @param {Object} log - 日志数据
     * @returns {Promise}
     */
    update_log(log) {
        return api.client.post('/log/update_log', log);
    }
};

export default log_api;