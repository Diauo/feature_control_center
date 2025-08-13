const { ref, computed } = Vue;

export function useFeatures(currentCustomer, currentUser, addNotification, api) {
    const features = ref([]);
    const activeFeature = ref(null);
    const featureRunning = ref(false);
    const consoleLogs = ref([]);
    
    // 功能注册相关数据
    const registerFeatureModal = ref({
        show: false,
        name: '',
        description: '',
        customer_id: '',
        category_id: 0,
        file: null
    });

    // 根据选择的客户和分类筛选功能
    const filteredFeatures = computed(() => {
        let result = features.value;

        if (currentCustomer.value) {
            result = result.filter(feature =>
                feature.customer_id === currentCustomer.value
            );
        }
        return result;
    });

    // 根据选择的客户加载功能
    const loadFeaturesByCustomer = async () => {
        if (!currentCustomer.value) {
            if (currentUser.value && currentUser.value.role === 'admin') {
                const response = await api.feature.get_all_feature();
                if (response.data.status) {
                    features.value = response.data.data;
                } else {
                    addNotification(response.data.message || '加载功能列表失败');
                }
            } else {
                features.value = [];
            }
            return;
        }
        
        try {
            const response = await api.feature.get_feature_by_customer_id(currentCustomer.value);
            if (response.data.status) {
                features.value = response.data.data;
            } else {
                addNotification(response.data.message || '加载功能列表失败');
            }
        } catch (error) {
            addNotification('加载功能时发生错误: ' + error.message);
        }
    };

    // 打开功能窗口
    const openFeatureWindow = (feature) => {
        activeFeature.value = feature;
        consoleLogs.value = [];
        addConsoleLog('准备运行 ' + feature.name, 'info');
    };

    // 关闭功能窗口
    const closeFeatureWindow = () => {
        if (featureRunning.value) {
            if (confirm('功能正在运行中，确定要关闭窗口吗？')) {
                stopFeature();
            } else {
                return;
            }
        }
        activeFeature.value = null;
        featureRunning.value = false;
        consoleLogs.value = [];
    };

    // 添加控制台日志
    const addConsoleLog = (message, type = 'info') => {
        consoleLogs.value.push({
            message: `[${new Date().toLocaleTimeString()}] ${message}`,
            type
        });
        
        setTimeout(() => {
            const consoleOutput = document.querySelector('.console-output');
            if (consoleOutput) {
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
            }
        }, 0);
    };

    // 运行功能
    const runFeature = () => {
        if (featureRunning.value) {
            addConsoleLog(`功能 ${activeFeature.value.name} 已在运行中，请等待完成`, 'warn');
            addNotification(`功能 ${activeFeature.value.name} 已在运行中，请等待完成`);
            return;
        }

        featureRunning.value = true;

        // 生成唯一 client_id
        const clientId = window.getClientUUID ? window.getClientUUID() : Math.random().toString(36).substr(2, 9);

        // 连接到 WebSocket 服务
        const socket = io('/feature');
        
        socket.on('connect', () => {
            console.log("✅ WebSocket 已连接");
            socket.emit('register', { client_id: clientId });
            
            api.feature.execute_feature(activeFeature.value.id, clientId).then(response => {
                const data = response.data;
                if (data.status) {
                    addConsoleLog(`功能 ${activeFeature.value.name} 执行中`, 'info');
                } else {
                    addConsoleLog(`功能 ${activeFeature.value.name} 执行失败: ${data.data}`, 'error');
                    addNotification(data.message || `功能 ${activeFeature.value.name} 执行失败`);
                    featureRunning.value = false;
                    socket.disconnect();
                }
            }).catch(error => {
                addConsoleLog(`功能 ${activeFeature.value.name} 执行异常: ${error.message}`, 'error');
                addNotification(error.message || `功能 ${activeFeature.value.name} 执行异常`);
                featureRunning.value = false;
                socket.disconnect();
            });
        });

        socket.on('log', (data) => {
            addConsoleLog(data.message, 'info');
        });

        socket.on('disconnect', () => {
            featureRunning.value = false;
            console.log("⚡ WebSocket 已断开连接");
        });

        socket.on('feature_done', (data) => {
            featureRunning.value = false;
            if (data.status === 'success') {
                addConsoleLog(`完成： ${data.msg}`, 'info');
                addNotification(data.message || `${activeFeature.value.name} 执行成功`);
            } else {
                addConsoleLog(`失败：${data.msg}`, 'error');
                addNotification(data.message || `${activeFeature.value.name} 执行失败`);
            }
            socket.disconnect();
        });
    };

    // 停止功能
    const stopFeature = () => {
        featureRunning.value = false;
        addConsoleLog('功能运行已终止', 'warning');
        addNotification(`${activeFeature.value.name}已停止运行`);
    };

    // 删除功能 - 第一次确认
    const confirmDeleteFeature = () => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以删除功能');
            return;
        }
        
        if (confirm(`确定要删除功能 "${activeFeature.value.name}" 吗？\n\n点击"确定"继续删除操作。`)) {
            setTimeout(() => {
                if (confirm(`请再次确认：确定要删除功能 "${activeFeature.value.name}" 吗？\n\n注意：此操作不可恢复！`)) {
                    deleteFeature();
                }
            }, 100);
        }
    };

    // 删除功能 - 执行删除
    const deleteFeature = async () => {
        try {
            const response = await api.feature.delete_feature(activeFeature.value.id);
            if (response.data.status) {
                addNotification(response.data.message || '功能删除成功');
                closeFeatureWindow();
                
                const featureResponse = await api.feature.get_all_feature();
                if (featureResponse.data.status) {
                    features.value = featureResponse.data.data;
                }
            } else {
                addNotification(response.data.message || '功能删除失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('删除功能时发生错误:', error);
            addNotification('删除功能时发生错误: ' + error.message);
        }
    };

    // 打开注册功能模态框
    const openRegisterFeatureModal = () => {
        if (!currentUser.value || currentUser.value.role !== 'admin') {
            addNotification('权限不足：只有管理员可以注册功能');
            return;
        }
        registerFeatureModal.value.show = true;
    };
    
    // 关闭注册功能模态框
    const closeRegisterFeatureModal = () => {
        registerFeatureModal.value.show = false;
        registerFeatureModal.value.name = '';
        registerFeatureModal.value.description = '';
        registerFeatureModal.value.customer_id = '';
        registerFeatureModal.value.category_id = 0;
        registerFeatureModal.value.file = null;
    };
    
    // 处理文件上传
    const handleFileUpload = (event) => {
        const file = event.target.files[0];
        if (!file) return;
        
        // 检查文件类型
        if (!file.name.endsWith('.py')) {
            addNotification('请选择Python文件(.py)');
            return;
        }
        
        registerFeatureModal.value.file = file;
    };
    
    // 注册功能
    const registerFeature = async () => {
        if (!registerFeatureModal.value.file) {
            addNotification('请先选择功能脚本文件');
            return;
        }
        
        if (!registerFeatureModal.value.name) {
            addNotification('请输入功能名称');
            return;
        }
        
        try {
            const formData = new FormData();
            formData.append('file', registerFeatureModal.value.file);
            formData.append('name', registerFeatureModal.value.name);
            formData.append('description', registerFeatureModal.value.description);
            formData.append('customer_id', registerFeatureModal.value.customer_id);
            formData.append('category_id', registerFeatureModal.value.category_id);
            
            const response = await api.feature.register_feature(formData);
            
            if (response.data.status) {
                addNotification(response.data.message || '功能注册成功');
                closeRegisterFeatureModal();
                
                const featureResponse = await api.feature.get_all_feature();
                if (featureResponse.data.status) {
                    features.value = featureResponse.data.data;
                }
            } else {
                addNotification(response.data.message || '功能注册失败: ' + response.data.data);
            }
        } catch (error) {
            console.error('注册功能时发生错误:', error);
            addNotification('注册功能时发生错误: ' + error.message);
        }
    };

    return {
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
    };
}
        