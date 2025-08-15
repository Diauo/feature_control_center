import api from './api.js';

const log_api = {
    /**
     * 查询日志
     * @param {Object} params - 查询参数
     * @param {number} params.feature_id - 功能ID
     * @param {string} params.start_date - 开始日期
     * @param {string} params.end_date - 结束日期
     * @param {string} params.keyword - 关键字
     * @param {string} params.execution_type - 执行类型 (manual/scheduled)
     * @returns {Promise}
     */
    query(params) {
        return api.client.get('/log/query', { params });
    },

    /**
     * 获取日志明细内容
     * @param {number} id - 日志ID
     * @returns {Promise}
     */
    getLogDetails(id) {
        return api.client.get('/log/get_log_details', { params: { id } });
    }
};

export default log_api;