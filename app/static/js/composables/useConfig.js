const { ref } = Vue;

export function useConfig(currentUser, addNotification, api) {
    const configs = ref([]);
    const configModal = ref({
        show: false,
        title: '',
        mode: 'add', // 'add' 或 'edit'
        formData: {
            id: null,
            name: '',
            value: '',
            description: '',
            feature_id: 0
        }
    });
    
    // 筛选条件
    const filterConditions = ref({
        feature_id: '',
        feature_name: '',
        config_name: '',
        config_description: ''
    });

    // 加载所有配置
    const loadConfigs = async () => {
        try {
            const response = await api.config.get_all_config();
            if (response.data.status) {
                configs.value = response.data.data;
            } else {
                console.error('加载配置失败:', response.data.data);
                addNotification(response.data.message || '加载配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('加载配置时发生错误:', error);
            addNotification('加载配置时发生错误: ' + error.message);
        }
    };
    
    // 根据筛选条件加载配置
    const loadFilteredConfigs = async () => {
        try {
            const params = {};
            if (filterConditions.value.feature_id !== '') {
                params.feature_id = filterConditions.value.feature_id;
            }
            if (filterConditions.value.feature_name) {
                params.feature_name = filterConditions.value.feature_name;
            }
            if (filterConditions.value.config_name) {
                params.config_name = filterConditions.value.config_name;
            }
            if (filterConditions.value.config_description) {
                params.config_description = filterConditions.value.config_description;
            }
            
            const response = await api.config.get_filtered_config(params);
            if (response.data.status) {
                configs.value = response.data.data;
            } else {
                console.error('加载筛选配置失败:', response.data.data);
                addNotification(response.data.message || '加载筛选配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('加载筛选配置时发生错误:', error);
            addNotification('加载筛选配置时发生错误: ' + error.message);
        }
    };
    
    // 重置筛选条件
    const resetFilterConditions = () => {
        filterConditions.value = {
            feature_id: '',
            feature_name: '',
            config_name: '',
            config_description: ''
        };
    };

    // 打开添加配置模态框
    const openAddConfigModal = () => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以添加配置');
            return;
        }
        
        configModal.value.mode = 'add';
        configModal.value.title = '添加配置';
        configModal.value.formData = {
            id: null,
            name: '',
            value: '',
            description: '',
            feature_id: 0
        };
        configModal.value.show = true;
    };

    // 打开编辑配置模态框
    const openEditConfigModal = (config) => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以编辑配置');
            return;
        }
        
        configModal.value.mode = 'edit';
        configModal.value.title = '编辑配置';
        configModal.value.formData = {
            id: config.id,
            name: config.name,
            value: config.value,
            default_value: config.default_value,
            description: config.description,
            feature_id: config.feature_id || 0
        };
        configModal.value.show = true;
    };

    // 关闭配置模态框
    const closeConfigModal = () => {
        configModal.value.show = false;
        configModal.value.formData = {
            id: null,
            name: '',
            value: '',
            description: '',
            feature_id: 0
        };
    };

    // 保存配置
    const saveConfig = async () => {
        try {
            let response;
            if (configModal.value.mode === 'add') {
                response = await api.config.add_config(configModal.value.formData);
            } else {
                debugger;
                response = await api.config.update_config(
                    configModal.value.formData
                );
            }

            if (response.data.status) {
                addNotification(
                    response.data.message || 
                    (configModal.value.mode === 'add' ? '配置添加成功' : '配置更新成功')
                );
                closeConfigModal();
                await loadConfigs();
            } else {
                console.error('保存配置失败:', response.data.data);
                addNotification(response.data.message || '保存配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('保存配置时发生错误:', error);
            addNotification('保存配置时发生错误: ' + error.message);
        }
    };

    // 删除配置
    const deleteConfig = async (config) => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以删除配置');
            return;
        }
        
        if (!confirm('确定要删除这个配置吗？')) {
            return;
        }

        try {
            const response = await api.config.delete_config(config.id);
            if (response.data.status) {
                addNotification(response.data.message || '配置删除成功');
                await loadConfigs();
            } else {
                console.error('删除配置失败:', response.data.data);
                addNotification(response.data.message || '删除配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('删除配置时发生错误:', error);
            addNotification('删除配置时发生错误: ' + error.message);
        }
    };

    // 重新加载配置
    const reloadConfig = async () => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以重载配置');
            return;
        }
        
        try {
            const response = await api.config.reload();
            if (response.data.status) {
                await loadConfigs();
                addNotification(response.data.message || '配置已重新加载');
            } else {
                console.error('重载配置失败:', response.data.data);
                addNotification(response.data.message || '重载配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('重载配置时发生错误:', error);
            addNotification('重载配置时发生错误: ' + error.message);
        }
    };

    // 清理无效配置
    const cleanupConfig = async () => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以清理配置');
            return;
        }
        
        if (!confirm('确定要清理无效配置吗？此操作不可恢复。')) {
            return;
        }

        try {
            const response = await api.config.cleanup();
            if (response.data.status) {
                addNotification(response.data.message || '无效配置清理成功');
                await loadConfigs();
            } else {
                console.error('清理无效配置失败:', response.data.data);
                addNotification(response.data.message || '清理无效配置失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('清理无效配置时发生错误:', error);
            addNotification('清理无效配置时发生错误: ' + error.message);
        }
    };

    return {
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
    };
}