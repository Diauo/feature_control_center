// axios is included via script tag, so we use the global axios object
const axios = window.axios;
import authService from '../services/authService.js';
import { useNotifications } from '../composables/useNotifications.js';
// 创建axios实例
const apiClient = axios.create({
    baseURL: '/api',
    timeout: 10000,
});

const { addNotification } = useNotifications();

// 请求拦截器
apiClient.interceptors.request.use(
    (config) => {
        // 添加认证令牌到请求头
        const token = authService.getAccessToken();
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// 响应拦截器
apiClient.interceptors.response.use(
    (response) => {
        return response;
    },
    async (error) => {
        const originalRequest = error.config;
        
        // 如果是401未授权错误，且不是刷新令牌请求
        if (error.response?.status === 401 && !originalRequest._retry) {
            // 检查是否是刷新令牌请求
            if (originalRequest.url.includes('/refresh')) {
                // 刷新令牌也失败了，清除本地令牌并重定向到登录页
                authService.clearTokens();
                window.location.href = '/login';
                return Promise.reject(error);
            }
            
            // 标记已重试
            originalRequest._retry = true;
            
            // 尝试刷新令牌
            const refreshSuccess = await authService.refreshAccessToken();
            if (refreshSuccess) {
                // 刷新成功，重新发送原始请求
                return apiClient(originalRequest);
            } else {
                // 刷新失败，重定向到登录页
                window.location.href = '/login';
            }
        }
        
        // 如果是403权限不足错误
        if (error.response?.status === 403) {
            // 显示权限不足的错误消息
            console.error('Permission denied:', error.response?.data || 'You do not have permission to perform this action.');
            // 可以在这里添加全局的错误提示，比如显示一个通知
            addNotification('权限不足', '您没有执行此操作的权限', 'error');
        }
        
        return Promise.reject(error);
    }
);

// 导入各个模块的API
import category_api from './category_api.js';
import customer_api from './customer_api.js';
import feature_api from './feature_api.js';
import user_api from './user_api.js';
import config_api from './config_api.js'; // 新增配置API
import log_api from './log_api.js'; // 新增日志API
import scheduled_task_api from './scheduled_task_api.js'; // 新增定时任务API

const api = {
    category: category_api,
    customer: customer_api,
    feature: feature_api,
    user: user_api,
    log: log_api, // 新增日志API
    config: config_api, // 新增配置API
    scheduledTask: scheduled_task_api, // 新增定时任务API
    client: apiClient // 导出axios实例，供直接使用
};

export default api;