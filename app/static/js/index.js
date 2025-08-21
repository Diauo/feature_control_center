const { createApp, ref, computed, onMounted, provide, nextTick, watch } = Vue
import api from './api/api.js';
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
import { useScheduledTasks } from './composables/useScheduledTasks.js';

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
            toggleCategory,
            toggleCategoryEdite,
            selectCategory,
            addCategory,
            delCategory,
            openAddCategoryModal
        } = useCategories(currentUser, currentCustomer, addNotification, openModal, closeModal, modal, api);
        
        // 处理分类切换并加载相应的功能
        const handleCategoryToggle = async (category) => {
            const result = await toggleCategory(category);
            
            if (result && result.type === 'reloadFeatures') {
                // 根据返回的指令加载功能
                if (result.method === 'all') {
                    // 加载所有功能
                    await loadFeaturesByCustomer();
                } else if (result.method === 'customer' && result.customerId) {
                    // 根据客户ID加载功能
                    const response = await api.feature.get_feature_by_customer_id(result.customerId);
                    if (response.data.status) {
                        features.value = response.data.data;
                    } else {
                        addNotification(response.data.message || '加载功能列表失败');
                    }
                } else if (result.method === 'category') {
                    // 根据分类ID加载功能
                    const response = await api.feature.get_feature_by_category_id(
                        result.categoryId,
                        result.customerId !== undefined ? result.customerId : null
                    );
                    if (response.data.status) {
                        features.value = response.data.data;
                    } else {
                        addNotification(response.data.message || '加载功能列表失败');
                    }
                }
            } else if (result && result.type === 'error') {
                // 处理错误情况
                addNotification(result.message || '操作失败');
            }
        };
        
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
            filterConditions,
            loadConfigs,
            loadFilteredConfigs,
            resetFilterConditions,
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
        
        // 定时任务筛选
        const scheduledTaskFilter = ref('');
        
        const {
            scheduledTasks,
            scheduledTasksLoading,
            scheduledTaskModal,
            loadScheduledTasks,
            openAddScheduledTaskModal,
            openEditScheduledTaskModal,
            closeScheduledTaskModal,
            saveScheduledTask,
            deleteScheduledTask,
            enableScheduledTask,
            disableScheduledTask,
            filteredScheduledTasks
        } = useScheduledTasks(addNotification, features, scheduledTaskFilter);
        
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


        // 页面切换方法
        const switchToHome = async () => {
            currentPage.value = 'home';
            await loadFeaturesByCustomer();
            
            // 重新加载分类数据
            const response = await api.category.get_all_category();
            if (response.data.status) {
                categories.value = response.data.data;
            } else {
                addNotification(response.data.message || '加载分类列表失败');
            }
        };
        
        const switchToConfig = async () => {
            currentPage.value = 'config';
            await loadConfigs();
            // 加载所有功能列表用于筛选
            await loadFeaturesByCustomer();
        };
        
        const switchToLogs = async () => {
            currentPage.value = 'logs';
            await loadLogs();
        };
        
        const switchToCron = async () => {
            currentPage.value = 'cron';
            await loadScheduledTasks();
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
            } else {
                addNotification(response.data.message || '加载分类列表失败');
            }
            
            // 加载配置
            await loadConfigs();
            
            // 加载定时任务
            await loadScheduledTasks();
            
            // 加载功能列表用于配置筛选
            await loadFeaturesByCustomer();
        });

        // 格式化时间显示
        const formatDateTime = (dateString) => {
            if (!dateString) return '-';
            const date = new Date(dateString);
            return date.toLocaleString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        };

        // 格式化日期显示
        const formatDate = (dateString) => {
            if (!dateString) return '-';
            const date = new Date(dateString);
            return date.toLocaleDateString('zh-CN', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit'
            });
        };

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
            handleCategoryToggle,
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
            filterConditions,
            loadConfigs,
            loadFilteredConfigs,
            resetFilterConditions,
            openAddConfigModal,
            openEditConfigModal,
            closeConfigModal,
            saveConfig,
            deleteConfig,
            reloadConfig,
            cleanupConfig,
            
            // 页面切换
            switchToHome,
            switchToConfig,
            switchToLogs,
            switchToCron,
            
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
            resetQueryConditions,
            
            // 定时任务相关
            scheduledTasks,
            scheduledTasksLoading,
            scheduledTaskModal,
            loadScheduledTasks,
            openAddScheduledTaskModal,
            openEditScheduledTaskModal,
            closeScheduledTaskModal,
            saveScheduledTask,
            deleteScheduledTask,
            enableScheduledTask,
            disableScheduledTask,
            formatDateTime,
            formatDate,
            // 定时任务筛选
            scheduledTaskFilter,
            filteredScheduledTasks
        }
    }
}).component('sidebar-menu', SidebarMenu).mount('#app');