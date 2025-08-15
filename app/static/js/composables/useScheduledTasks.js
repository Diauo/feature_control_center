const { ref, computed } = Vue
import api from '../api/api.js';

export function useScheduledTasks(addNotification, features) {
    // 定时任务相关状态
    const scheduledTasks = ref([]);
    const scheduledTasksLoading = ref(false);
    const scheduledTaskModal = ref({
        show: false,
        mode: 'add', // 'add' 或 'edit'
        formData: {
            id: null,
            name: '',
            feature_id: null,
            cron_expression: '',
            description: '',
            is_active: true
        }
    });
    
    // 加载定时任务列表
    const loadScheduledTasks = async () => {
        scheduledTasksLoading.value = true;
        try {
            const response = await api.scheduledTask.getAllScheduledTasks();
            if (response.data.status) {
                scheduledTasks.value = response.data.data || [];
            } else {
                addNotification(response.data.message || '加载定时任务列表失败');
            }
        } catch (error) {
            addNotification('加载定时任务列表时发生错误: ' + error.message);
        } finally {
            scheduledTasksLoading.value = false;
        }
    };
    
    // 打开新增定时任务模态框
    const openAddScheduledTaskModal = () => {
        scheduledTaskModal.value = {
            show: true,
            mode: 'add',
            formData: {
                id: null,
                name: '',
                feature_id: null,
                cron_expression: '',
                description: '',
                is_active: true
            }
        };
    };
    
    // 打开编辑定时任务模态框
    const openEditScheduledTaskModal = (task) => {
        scheduledTaskModal.value = {
            show: true,
            mode: 'edit',
            formData: {
                id: task.id,
                name: task.name,
                feature_id: task.feature_id,
                cron_expression: task.cron_expression,
                description: task.description,
                is_active: task.is_active
            }
        };
    };
    
    // 关闭定时任务模态框
    const closeScheduledTaskModal = () => {
        scheduledTaskModal.value.show = false;
    };
    
    // 保存定时任务
    const saveScheduledTask = async () => {
        try {
            let response;
            if (scheduledTaskModal.value.mode === 'edit') {
                // 编辑定时任务
                response = await api.scheduledTask.updateScheduledTask(scheduledTaskModal.value.formData.id, scheduledTaskModal.value.formData);
            } else {
                // 新增定时任务
                response = await api.scheduledTask.addScheduledTask(scheduledTaskModal.value.formData);
            }
            
            if (response.data.status) {
                addNotification(scheduledTaskModal.value.mode === 'edit' ? '定时任务更新成功' : '定时任务创建成功');
                closeScheduledTaskModal();
                await loadScheduledTasks();
            } else {
                addNotification(response.data.message || (scheduledTaskModal.value.mode === 'edit' ? '定时任务更新失败' : '定时任务创建失败'));
            }
        } catch (error) {
            addNotification((scheduledTaskModal.value.mode === 'edit' ? '定时任务更新时发生错误: ' : '定时任务创建时发生错误: ') + error.message);
        }
    };
    
    // 删除定时任务
    const deleteScheduledTask = async (id) => {
        if (!confirm('确定要删除这个定时任务吗？')) {
            return;
        }
        
        try {
            const response = await api.scheduledTask.deleteScheduledTask(id);
            if (response.data.status) {
                addNotification('定时任务删除成功');
                await loadScheduledTasks();
            } else {
                addNotification(response.data.message || '定时任务删除失败');
            }
        } catch (error) {
            addNotification('定时任务删除时发生错误: ' + error.message);
        }
    };
    
    // 启用定时任务
    const enableScheduledTask = async (id) => {
        try {
            const response = await api.scheduledTask.enableScheduledTask(id);
            if (response.data.status) {
                addNotification('定时任务启用成功');
                await loadScheduledTasks();
            } else {
                addNotification(response.data.message || '定时任务启用失败');
            }
        } catch (error) {
            addNotification('定时任务启用时发生错误: ' + error.message);
        }
    };
    
    // 禁用定时任务
    const disableScheduledTask = async (id) => {
        try {
            const response = await api.scheduledTask.disableScheduledTask(id);
            if (response.data.status) {
                addNotification('定时任务禁用成功');
                await loadScheduledTasks();
            } else {
                addNotification(response.data.message || '定时任务禁用失败');
            }
        } catch (error) {
            addNotification('定时任务禁用时发生错误: ' + error.message);
        }
    };
    
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

    return {
        // 状态
        scheduledTasks,
        scheduledTasksLoading,
        scheduledTaskModal,
        
        // 方法
        loadScheduledTasks,
        openAddScheduledTaskModal,
        openEditScheduledTaskModal,
        closeScheduledTaskModal,
        saveScheduledTask,
        deleteScheduledTask,
        enableScheduledTask,
        disableScheduledTask,
        
        // 工具函数
        formatDateTime,
        formatDate,
        
        // 数据
        features
    };
}