const { createApp, ref, computed, onMounted, provide, nextTick, watch } = Vue
import api from './api/api.js';
import { getClientUUID } from './utils.js';
import SidebarMenu from './composables/defineComponent.js';
import authService from './services/authService.js';
import { useNotifications } from './composables/useNotifications.js';
import { useModal } from './composables/useModal.js';
import { useFeatures } from './composables/useFeatures.js';
import { useCategories } from './composables/useCategories.js';
import { useConfig } from './composables/useConfig.js';
import { useCustomers } from './composables/useCustomers.js';
import { useAuth } from './composables/useAuth.js';
import { useLogs } from './composables/useLogs.js';

createApp({
    setup() {
        // 页面状态
        const currentPage = ref('home');
        const currentUser = ref(null);
        
        // 组合式函数
        const { notifications, notificationCount, addNotification, removeNotification } = useNotifications();
        const { modal, modalWindow, openModal, closeModal } = useModal();
        const { 
            currentCustomer, 
            customers, 
            getCurrentClientName,
            loadCustomers 
        } = useCustomers();
        
        const {
            categories,
            selectedCategory,
            categorieEditMode,
            filteredCategories,
            buildCategoryReferenceMap,
            toggleCategory,
            toggleCategoryEdite,
            selectCategory,
            addCategory,
            delCategory,
            openAddCategoryModal
        } = useCategories(currentCustomer, addNotification, openModal, closeModal, modal, api);
        
        const {
            features,
            activeFeature,
            featureRunning,
            consoleLogs,
            filteredFeatures,
            registerFeatureModal,
            loadFeaturesByCustomer,
            openFeatureWindow,
            closeFeatureWindow,
            runFeature,
            stopFeature,
            confirmDeleteFeature,
            deleteFeature,
            openRegisterFeatureModal,
            closeRegisterFeatureModal,
            handleFileUpload,
            registerFeature
        } = useFeatures(currentCustomer, currentUser, addNotification, api);
        
        const {
            configs,
            configModal,
            loadConfigs,
            openAddConfigModal,
            openEditConfigModal,
            closeConfigModal,
            saveConfig,
            deleteConfig,
            reloadConfig,
            cleanupConfig
        } = useConfig(currentUser, addNotification, api);
        
        const { logout } = useAuth(authService, api);
        
        const {
            logs: logList,
            logDetailList,
            loading: logsLoading,
            queryConditions,
            loadLogs,
            loadLogDetailList,
            setQueryConditions,
            resetQueryConditions
        } = useLogs(addNotification);
        
        // 日志明细筛选相关
        const logDetailFilter = ref('');
        const filteredLogDetails = ref([]);
        
        // 筛选日志明细
        const filterLogDetails = () => {
            if (!logDetailFilter.value) {
                filteredLogDetails.value = logDetailList.value;
                return;
            }
            
            try {
                const regex = new RegExp(logDetailFilter.value, 'i');
                filteredLogDetails.value = logDetailList.value.filter(detail =>
                    regex.test(detail.message)
                );
            } catch (e) {
                addNotification('正则表达式格式错误: ' + e.message);
                filteredLogDetails.value = logDetailList.value;
            }
        };
        
        // 清除日志明细筛选
        const clearLogDetailFilter = () => {
            logDetailFilter.value = '';
            filteredLogDetails.value = logDetailList.value;
        };
        
        // 当logDetailList变化时，更新filteredLogDetails
        watch(logDetailList, (newList) => {
            filteredLogDetails.value = newList;
        });

        // 监听客户选择变化
        watch(currentCustomer, async (newCustomer, oldCustomer) => {
            await loadFeaturesByCustomer();
        });

        // 定时任务相关
        const cronExpression = ref('');
        const logs = ref([
            { id: 1, message: '系统启动 - 2024-03-12 10:00:00' },
            { id: 2, message: '功能1执行成功 - 2024-03-12 10:05:00' },
            { id: 3, message: '定时任务更新 - 2024-03-12 10:10:00' },
        ]);

        // 保存定时任务
        const saveCronJob = () => {
            addNotification('定时任务已保存');
        };

        // 页面切换方法
        const switchToHome = async () => {
            currentPage.value = 'home';
            await loadFeaturesByCustomer();
            
            // 重新加载分类数据
            const response = await api.category.get_all_category();
            if (response.data.status) {
                categories.value = response.data.data;
                buildCategoryReferenceMap(categories.value);
            } else {
                addNotification(response.data.message || '加载分类列表失败');
            }
        };
        
        const switchToConfig = async () => {
            currentPage.value = 'config';
            await loadConfigs();
        };
        
        const switchToLogs = async () => {
            currentPage.value = 'logs';
            await loadLogs();
        };

        // 初始化
        onMounted(async () => {
            // 检查认证状态
            if (!authService.isAuthenticated()) {
                window.location.href = '/login';
                return;
            }
            
            // 检查令牌是否过期
            if (authService.isTokenExpired()) {
                const refreshSuccess = await authService.refreshAccessToken();
                if (!refreshSuccess) {
                    window.location.href = '/login';
                    return;
                }
            }
            
            // 获取当前用户信息
            currentUser.value = authService.getCurrentUser();
            
            // 加载所有数据
            await loadCustomers(api, addNotification);
            await loadFeaturesByCustomer();
            
            // 获取所有分类
            const response = await api.category.get_all_category();
            if (response.data.status) {
                categories.value = response.data.data;
                buildCategoryReferenceMap(categories.value);
            } else {
                addNotification(response.data.message || '加载分类列表失败');
            }
            
            // 加载配置
            await loadConfigs();
        });

        // 提供依赖注入
        provide('openAddCategoryModal', openAddCategoryModal);
        provide('toggleCategory', toggleCategory);
        provide('toggleCategoryEdite', toggleCategoryEdite);
        provide('categorieEditMode', categorieEditMode);
        
        return {
            // 页面状态
            currentPage,
            currentUser,
            
            // 通知相关
            notifications,
            addNotification,
            removeNotification,
            
            // 模态框相关
            modal,
            modalWindow,
            openModal,
            closeModal,
            
            // 客户相关
            currentCustomer,
            customers,
            getCurrentClientName,
            
            // 分类相关
            categories,
            selectedCategory,
            categorieEditMode,
            filteredCategories,
            toggleCategory,
            selectCategory,
            openAddCategoryModal,
            toggleCategoryEdite,
            
            // 功能相关
            features,
            activeFeature,
            featureRunning,
            consoleLogs,
            filteredFeatures,
            registerFeatureModal,
            openFeatureWindow,
            closeFeatureWindow,
            runFeature,
            stopFeature,
            confirmDeleteFeature,
            deleteFeature,
            openRegisterFeatureModal,
            closeRegisterFeatureModal,
            handleFileUpload,
            registerFeature,
            loadFeaturesByCustomer,
            
            // 配置相关
            configs,
            configModal,
            openAddConfigModal,
            openEditConfigModal,
            closeConfigModal,
            saveConfig,
            deleteConfig,
            reloadConfig,
            cleanupConfig,
            
            // 定时任务相关
            cronExpression,
            logs,
            saveCronJob,
            
            // 页面切换
            switchToHome,
            switchToConfig,
            switchToLogs,
            
            // 认证相关
            logout,
            
            // 日志相关
            logList,
            logDetailList,
            logDetailFilter,
            filteredLogDetails,
            logsLoading,
            queryConditions,
            loadLogs,
            loadLogDetailList,
            filterLogDetails,
            clearLogDetailFilter,
            setQueryConditions,
            resetQueryConditions
        }
    }
}).component('sidebar-menu', SidebarMenu).mount('#app');