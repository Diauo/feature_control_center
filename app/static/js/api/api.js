// axios is included via script tag, so we use the global axios object
const axios = window.axios;
import authService from '../services/authService.js';

// 创建axios实例
const apiClient = axios.create({
    baseURL: '/api',
    timeout: 10000,
});

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
        
        return Promise.reject(error);
    }
);

// 导入各个模块的API
import category_api from './category_api.js';
import customer_api from './customer_api.js';
import feature_api from './feature_api.js';
import user_api from './user_api.js';
import config_api from './config_api.js'; // 新增配置API

const api = {
    category: category_api,
    customer: customer_api,
    feature: feature_api,
    user: user_api,
    config: config_api, // 新增配置API
    client: apiClient // 导出axios实例，供直接使用
};

export default api;