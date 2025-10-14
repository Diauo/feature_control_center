const { ref, computed } = Vue
import api from '../api/api.js';

export function useLogs(addNotification) {
    // 日志相关状态
    const logs = ref([]);
    const logDetailList = ref([]);
    const loading = ref(false);
    
    // 查询条件
    const queryConditions = ref({
        feature_id: null,
        start_date: null,
        end_date: null,
        keyword: null,
        execution_type: null
    });
    
    // 加载日志列表
    const loadLogs = async () => {
        loading.value = true;
        try {
            const response = await api.log.get_logs(queryConditions.value);
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
    
    
    // 获取日志明细内容
    const loadLogDetailList = async (logId) => {
        try {
            const response = await api.log.getLogDetails(logId);
            if (response.data.status) {
                logDetailList.value = response.data.data || [];
            } else {
                addNotification(response.data.message || '加载日志明细失败');
            }
            if( logDetailList.value.length === 0) {
                addNotification('没有找到相关日志明细');
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
            keyword: null,
            execution_type: null
        };
    };
    
    return {
        // 状态
        logs,
        logDetailList,
        loading,
        queryConditions,
        
        // 方法
        loadLogs,
        loadLogDetailList,
        setQueryConditions,
        resetQueryConditions
    };
}