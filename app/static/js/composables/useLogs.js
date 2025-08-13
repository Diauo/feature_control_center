const { ref, computed } = Vue
import api from '../api/api.js';

export function useLogs(addNotification) {
    // 日志相关状态
    const logs = ref([]);
    const logDetails = ref(null);
    const logDetailList = ref([]);  // 新增：存储日志明细列表
    const loading = ref(false);
    
    // 查询条件
    const queryConditions = ref({
        feature_id: null,
        start_date: null,
        end_date: null,
        keyword: null
    });
    
    // 加载日志列表
    const loadLogs = async () => {
        loading.value = true;
        try {
            const response = await api.log.query(queryConditions.value);
            if (response.data.status) {
                logs.value = response.data.data || [];
            } else {
                addNotification(response.data.message || '加载日志列表失败');
            }
        } catch (error) {
            addNotification('加载日志列表时发生错误: ' + error.message);
        } finally {
            loading.value = false;
        }
    };
    
    // 获取日志详细内容
    const loadLogDetails = async (logId) => {
        try {
            const response = await api.log.getLogContent(logId);
            if (response.data.status) {
                logDetails.value = response.data.data;
            } else {
                addNotification(response.data.message || '加载日志详情失败');
            }
        } catch (error) {
            addNotification('加载日志详情时发生错误: ' + error.message);
        }
    };
    
    // 获取日志明细内容
    const loadLogDetailList = async (logId) => {
        try {
            const response = await api.log.getLogDetails(logId);
            if (response.data.status) {
                logDetailList.value = response.data.data || [];
            } else {
                addNotification(response.data.message || '加载日志明细失败');
            }
        } catch (error) {
            addNotification('加载日志明细时发生错误: ' + error.message);
        }
    };
    
    // 设置查询条件
    const setQueryConditions = (conditions) => {
        queryConditions.value = { ...queryConditions.value, ...conditions };
    };
    
    // 重置查询条件
    const resetQueryConditions = () => {
        queryConditions.value = {
            feature_id: null,
            start_date: null,
            end_date: null,
            keyword: null
        };
    };
    
    return {
        // 状态
        logs,
        logDetails,
        logDetailList,  // 新增：返回日志明细列表
        loading,
        queryConditions,
        
        // 方法
        loadLogs,
        loadLogDetails,
        loadLogDetailList,  // 新增：返回加载日志明细的方法
        setQueryConditions,
        resetQueryConditions
    };
}