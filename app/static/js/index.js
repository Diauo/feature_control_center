const { createApp, ref, computed, onMounted, provide, nextTick } = Vue
import api from './api/api.js';
import SidebarMenu from './defineComponent.js';
import authService from './services/authService.js';

createApp({
    setup() {
        const currentPage = ref('home') // 当前页面
        const activeFeature = ref(null) // 当前激活的功能
        const notifications = ref([])   // 通知
        const cronExpression = ref('')  // cron表达式
        const notificationCount = ref(0)    // 通知数量
        const featureRunning = ref(false)   // 功能正在运行
        const consoleLogs = ref([])     // 日志列表
        const selectedCategory = ref(null)  // 选择的分类
        const categorieEditMode = ref(false)  // 编辑模式
        const modal = ref({ show: false, title: "", description: "", fields: [], buttons: [], modalParams: {}, top: 0, left: 0 })  // 弹窗
        const modalWindow = ref(null)
        const currentCustomer = ref('')     // 当前客户
        const customers = ref([])           // 所有客户
        const categories = ref([])          // 所有分类
        const categoriesReferenceMap = new Map()          // 分类映射Map
        const features = ref([]);           // 所有功能
        const currentUser = ref(null);      // 当前用户信息
        
        // 配置管理相关数据
        const configs = ref([]);            // 所有配置
        const configModal = ref({
            show: false,
            title: '',
            mode: 'add', // 'add' 或 'edit'
            formData: {
                id: null,
                key: '',
                value: '',
                description: '',
                feature_id: 0
            }
        });

        // 检查用户是否已认证
        onMounted(async () => {
            // 检查认证状态
            if (!authService.isAuthenticated()) {
                // 未认证，重定向到登录页面
                window.location.href = '/login';
                return;
            }
            
            // 检查令牌是否过期
            if (authService.isTokenExpired()) {
                // 尝试刷新令牌
                const refreshSuccess = await authService.refreshAccessToken();
                if (!refreshSuccess) {
                    // 刷新失败，重定向到登录页面
                    window.location.href = '/login';
                    return;
                }
            }
            
            // 获取当前用户信息
            currentUser.value = authService.getCurrentUser();
            
            // 获取所有功能
            let response = await api.feature.get_all_feature();
            if (response.data.status) {
                features.value = response.data.data;
            } else {
                addNotification(response.data.message || '加载功能列表失败');
            }
            // 获取所有客户
            response = await api.customer.get_all_customer();
            if (response.data.status) {
                customers.value = response.data.data;
            } else {
                addNotification(response.data.message || '加载客户列表失败');
            }
            // 获取所有分类
            response = await api.category.get_all_category();
            if (response.data.status) {
                categories.value = response.data.data;
                // 构建分类引用映射
                buildCategoryReferenceMap(categories.value);
            } else {
                addNotification(response.data.message || '加载分类列表失败');
            }
            
            // 加载配置
            await loadConfigs();
        })

        // 构建分类引用映射，用于通过映射直接修改节点
        const buildCategoryReferenceMap = (nodes) => {
            if (!nodes || !Array.isArray(nodes)) return;
            nodes.forEach((node) => {
                // 将当前节点存入 Map
                categoriesReferenceMap.set(node.id, node);
                // 递归处理子节点
                if (node.child && node.child.length > 0) {
                    buildCategoryReferenceMap(node.child);
                }
            });
        }

        const logs = ref([
            { id: 1, message: '系统启动 - 2024-03-12 10:00:00' },
            { id: 2, message: '功能1执行成功 - 2024-03-12 10:05:00' },
            { id: 3, message: '定时任务更新 - 2024-03-12 10:10:00' },
        ])


        // 根据选择的客户筛选分类
        // todo 没有选择具体客户的情况下，新增分类和功能可能无法设定归属
        const filteredCategories = computed(() => {
            if (!currentCustomer.value) {
                return categories.value
            }
            return categories.value.filter(category =>
                category.customer_id === currentCustomer.value
            )
        })

        // 根据选择的客户和分类筛选功能
        const filteredFeatures = computed(() => {
            let result = features.value

            if (currentCustomer.value) {
                result = result.filter(feature =>
                    feature.customer_id === currentCustomer.value
                )
            }
            // 根据标签分类
            if (selectedCategory.value) {
                result = result.filter(feature =>
                    feature.category.split(",").includes(selectedCategory.value)
                )
            }
            return result
        })

        // 获取当前客户名称
        const getCurrentClientName = computed(() => {
            if (!currentCustomer.value) return ''
            const client = customers.value.find(c => c.id === currentCustomer.value)
            return client ? client.name : ''
        })

        const toggleCategoryEdite = () => {
            categorieEditMode.value = !categorieEditMode.value
        }

        const addCategory = async (params) => {
            debugger
            let modalParams = modal.value.modalParams;
            const requestBody = {
                customer_id: params.customer_id,
                depth_level: params.depth_level + 1,
                parent_id: params.id,
                tags: modalParams.modalParams,
                name: modalParams.name,
                order_id: modalParams.order_id,
            }
            if (!requestBody.name) {
                alert("请输入新分类的名称！");
                return
            }
            let response = await api.category.add_category(requestBody);
            console.log(response)
            if (response.data.status) {
                // 刷新分类
                const parent = categoriesReferenceMap.get(params.id);
                if (parent) {
                    if (!parent.child) {
                        parent.child = [];
                    }
                    parent.child.push(response.data.data);
                } else {
                    // 新增的是0级分类，存入categories并将映射写入categoriesReferenceMap
                    let index = categories.value.push(response.data.data)
                    categoriesReferenceMap.set(response.data.data.id, categories[index])
                }
                closeModal()
                addNotification(response.data.message || "分类添加成功")
            } else {
                addNotification(response.data.message || "插入分类失败：" + response.data.data)
            }
        }

        const delCategory = async (params) => {
            debugger;
            const requestBody = {
                id: params.id
            }
            let response = await api.category.del_category(requestBody);
            if (response.data.status) {
                // 找到父级删除该子节点
                const parent = categoriesReferenceMap.get(params.parent_id);
                if (parent?.child) {
                    const childIndex = parent.child.findIndex(child => child.id === params.id);
                    if (childIndex !== -1) {
                        parent.child.splice(childIndex, 1);
                    }
                } else {
                    // 是0级节点，从categories里面删除
                    const index = categories.value.findIndex(categories => categories.id === params.id)
                    if (index !== -1) {
                        categories.value.splice(index, 1);
                    }
                    categoriesReferenceMap.delete(params.id)
                }
                closeModal()
                addNotification(response.data.message || "分类删除成功")
            } else {
                addNotification(response.data.message || "删除分类失败：" + response.data.data)
            }
        }
        // 打开新增分类窗口
        const openAddCategoryModal = (category, event) => {
            if (!category) {
                category = {
                    "customer_id": currentCustomer.value,
                    "depth_level": -1,
                    "id": 0,
                    "expanded": false
                }
            }
            let fields = [
                {
                    type: "text",
                    key: "name",
                    label: "名称",
                }, {
                    type: "text",
                    key: "order_id",
                    label: "排序",
                }
            ]
            let buttons = [
                {
                    label: "新增",
                    style: "btn-confirm",
                    function: addCategory,
                    param: category
                },
                {
                    label: "修改",
                    style: "btn-warnning",
                    function: closeModal,
                    param: category
                },
                {
                    label: "删除",
                    style: "btn-danger",
                    function: delCategory,
                    param: category
                }
            ]
            const buttonElement = event.currentTarget;
            openModal("分类菜单", "新增：根据填写的信息，在本分类下新增一个子菜单；\<br\>修改：根据填写的信息修改当前分类；\<br\>删除：删除当前分类。", fields, buttons, buttonElement)
        }

        const openModal = (title, description, fields, buttons, buttonElement) => {
            modal.value.title = title
            modal.value.fields = fields
            modal.value.description = description
            modal.value.buttons = buttons
            modal.value.show = true
            // 更新动态窗口的位置，避免超出屏幕
            nextTick(() => {
                if (modalWindow.value) {
                    const modalRect = modalWindow.value.getBoundingClientRect();
                    const modalWidth = modalRect.width;
                    const modalHeight = modalRect.height;
                    const buttonRect = buttonElement.getBoundingClientRect();
                    let top = buttonRect.top + window.scrollY;
                    let left = (buttonRect.left + window.scrollX) * 1.25;
                    // 检查是否超出屏幕底部
                    if (top + modalHeight > window.innerHeight + window.scrollY) {
                        top = window.innerHeight + window.scrollY - modalHeight;
                    }
                    // 检查是否超出屏幕右侧
                    if (left + modalWidth > window.innerWidth + window.scrollX) {
                        left = window.innerWidth + window.scrollX - modalWidth;
                    }
                    modal.value.top = top
                    modal.value.left = left
                }
            });

        }
        const closeModal = () => {
            modal.value.show = false
            modal.value.title = ""
            modal.value.fields = ""
            modal.value.description = ""
            modal.value.modalParams = {}
            modal.value.params = {}
            modal.value.hanldFunction = undefined
        }

        // 切换分类展开/收起
        const toggleCategory = (category) => {
            // 如果有子菜单，递归地折叠所有子菜单
            const collapseChildren = (cat) => {
                if (cat.child && cat.child.length > 0) {
                    cat.child.forEach(child => {
                        child.expanded = false;  // 折叠子菜单
                        collapseChildren(child); // 递归折叠
                    });
                }
            };

            // 切换当前类别的折叠状态
            category.expanded = !category.expanded;

            // 如果折叠了当前菜单，折叠它的所有子菜单
            if (!category.expanded) {
                collapseChildren(category);
            }

            // 同时标识选中了该分类，高亮该分类，并设置过滤标签
            selectCategory()
        }

        // 选择分类
        const selectCategory = (categoryCode) => {
            selectedCategory.value = categoryCode
        }

        // 打开功能窗口
        const openFeatureWindow = (feature) => {
            activeFeature.value = feature
            consoleLogs.value = [] // 清空之前的日志
            addConsoleLog('准备运行 ' + feature.name, 'info')
        }

        // 关闭功能窗口
        const closeFeatureWindow = () => {
            if (featureRunning.value) {
                if (confirm('功能正在运行中，确定要关闭窗口吗？')) {
                    stopFeature()
                } else {
                    return
                }
            }
            activeFeature.value = null
            featureRunning.value = false
            consoleLogs.value = []
        }

        // 运行功能
        const runFeature = () => {
            // 如果正在运行，则退出
            if (featureRunning.value) {
                addConsoleLog(`功能 ${activeFeature.value.name} 已在运行中，请等待完成`, 'warn')
                addNotification(`功能 ${activeFeature.value.name} 已在运行中，请等待完成`)
                return
            }

            featureRunning.value = true

            // 生成唯一 client_id
            let clientId = crypto.randomUUID();

            // 连接到 WebSocket 服务
            let socket = io('/feature')
            socket.on('connect', () => {
                console.log("✅ WebSocket 已连接")
                socket.emit('register', { client_id: clientId })  // 注册身份
                // 调用API执行功能
                api.feature.execute_feature(activeFeature.value.id, clientId).then(response => {
                    debugger;
                    const data = response.data
                    if (data.status) {
                        addConsoleLog(`功能 ${activeFeature.value.name} 执行中`, 'info')
                    } else {
                        addConsoleLog(`功能 ${activeFeature.value.name} 执行失败: ${data.data}`, 'error')
                        addNotification(data.message || `功能 ${activeFeature.value.name} 执行失败`)
                        featureRunning.value = false
                        socket.disconnect()
                    }
                }).catch(error => {
                    addConsoleLog(`功能 ${activeFeature.value.name} 执行异常: ${error.message}`, 'error')
                    addNotification(error.message || `功能 ${activeFeature.value.name} 执行异常`)
                    featureRunning.value = false
                    socket.disconnect()
                })
            })

            // 接收日志消息
            socket.on('log', (data) => {
                addConsoleLog(data.message, 'info')  // 追加日志到控制台区域
            })

            socket.on('disconnect', () => {
                featureRunning.value = false
                console.log("❎ WebSocket 已断开连接")
            })

            socket.on('feature_done', (data) => {
                featureRunning.value = false
                if (data.status === 'success') {
                    addConsoleLog(`完成： ${data.msg}`, 'info')
                    addNotification(data.message || `${activeFeature.value.name} 执行成功`)
                } else {
                    addConsoleLog(`失败：${data.msg}`, 'error')
                    addNotification(data.message || `${activeFeature.value.name} 执行失败`)
                }
                socket.disconnect()
            })


        }

        // 停止功能
        const stopFeature = () => {
            featureRunning.value = false
            addConsoleLog('功能运行已终止', 'warning')
            addNotification(`${activeFeature.value.name}已停止运行`)  // 这个是本地消息，不需要从响应中获取
        }

        // 添加控制台日志
        const addConsoleLog = (message, type = 'info') => {
            consoleLogs.value.push({
                message: `[${new Date().toLocaleTimeString()}] ${message}`,
                type
            })
            // 自动滚动到底部
            setTimeout(() => {
                const consoleOutput = document.querySelector('.console-output')
                if (consoleOutput) {
                    consoleOutput.scrollTop = consoleOutput.scrollHeight
                }
            }, 0)
        }

        // 模拟控制台输出
        const simulateConsoleOutput = () => {
            const messages = [
                { msg: '正在连接服务器...', type: 'info', delay: 1000 },
                { msg: '验证授权信息...', type: 'info', delay: 2000 },
                { msg: '开始处理数据...', type: 'info', delay: 3000 },
                { msg: '警告：发现部分数据不完整', type: 'warning', delay: 4000 },
                { msg: '正在重试处理...', type: 'info', delay: 5000 },
                { msg: '数据处理完成', type: 'info', delay: 6000 }
            ]

            messages.forEach(({ msg, type, delay }) => {
                setTimeout(() => {
                    if (featureRunning.value) { // 只有在仍在运行时才添加日志
                        addConsoleLog(msg, type)
                    }
                }, delay)
            })
        }

        // 添加通知
        const addNotification = (message) => {
            const now = new Date();
            const hours = ('0' + now.getHours()).slice(-2);
            const minutes = ('0' + now.getMinutes()).slice(-2);
            const seconds = ('0' + now.getSeconds()).slice(-2);
            const id = notificationCount.value++;
            message = "💡 " + hours + ":" + minutes + ":" + seconds + "\<br\>" + message
            notifications.value.push({
                id,
                message
            });
            setTimeout(() => {
                removeNotification(id);
            }, 10000);
        };

        const removeNotification = (id) => {
            notifications.value = notifications.value.filter(notification => notification.id !== id);
        };

        // 保存定时任务
        const saveCronJob = () => {
            addNotification('定时任务已保存')
        }

        // WebSocket连接通知
        // const connectWebSocket = () => {
        //     const ws = new WebSocket('ws://your-backend-url')
        //     ws.onmessage = (event) => {
        //         const data = JSON.parse(event.data)
        //         if (data.type === 'notification') {
        //             addNotification(data.message)
        //         } else if (data.type === 'console' && featureRunning.value) {
        //             addConsoleLog(data.message, data.logType || 'info')
        //         }
        //     }
        //     ws.onclose = () => {
        //         // 断线重连逻辑
        //         setTimeout(connectWebSocket, 3000)
        //     }
        // }
        // 启动WebSocket连接
        // connectWebSocket()

        // 配置管理方法
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

        // 打开添加配置模态框
        const openAddConfigModal = () => {
            // 检查用户是否有管理员权限
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                addNotification('权限不足：只有管理员可以添加配置');
                return;
            }
            
            configModal.value.mode = 'add';
            configModal.value.title = '添加配置';
            configModal.value.formData = {
                id: null,
                key: '',
                value: '',
                description: '',
                feature_id: 0
            };
            configModal.value.show = true;
        };

        // 打开编辑配置模态框
        const openEditConfigModal = (config) => {
            // 检查用户是否有管理员权限
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                addNotification('权限不足：只有管理员可以编辑配置');
                return;
            }
            
            configModal.value.mode = 'edit';
            configModal.value.title = '编辑配置';
            configModal.value.formData = {
                id: config.id,
                key: config.key,
                value: config.value,
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
                key: '',
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
                    // 添加配置
                    response = await api.config.add_config(configModal.value.formData);
                } else {
                    // 编辑配置
                    response = await api.config.update_config(configModal.value.formData.id, configModal.value.formData);
                }

                if (response.data.status) {
                    addNotification(response.data.message || (configModal.value.mode === 'add' ? '配置添加成功' : '配置更新成功'));
                    closeConfigModal();
                    await loadConfigs(); // 重新加载配置
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
        const deleteConfig = async (id) => {
            // 检查用户是否有管理员权限
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                addNotification('权限不足：只有管理员可以删除配置');
                return;
            }
            
            if (!confirm('确定要删除这个配置吗？')) {
                return;
            }

            try {
                const response = await api.config.delete_config(id);
                if (response.data.status) {
                    addNotification(response.data.message || '配置删除成功');
                    await loadConfigs(); // 重新加载配置
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
            // 检查用户是否有管理员权限
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                addNotification('权限不足：只有管理员可以重载配置');
                return;
            }
            
            try {
                const response = await api.config.reload();
                if (response.data.status) {
                    await loadConfigs(); // 重新加载配置
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
            // 检查用户是否有管理员权限
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
                    await loadConfigs(); // 重新加载配置
                } else {
                    console.error('清理无效配置失败:', response.data.data);
                    addNotification(response.data.message || '清理无效配置失败: ' + response.data.data);
                }
            } catch (error) {
                console.error('清理无效配置时发生错误:', error);
                addNotification('清理无效配置时发生错误: ' + error.message);
            }
        };

        provide('openAddCategoryModal', openAddCategoryModal);
        // 用户登出
        const logout = async () => {
            try {
                // 调用后端登出接口
                await api.user.logout();
            } catch (error) {
                console.error('Logout error:', error);
            } finally {
                // 清除本地令牌
                authService.clearTokens();
                // 重定向到登录页面
                window.location.href = '/login';
            }
        };

        provide('toggleCategory', toggleCategory);
        provide('toggleCategoryEdite', toggleCategoryEdite);
        provide('categorieEditMode', categorieEditMode);
        return {
            // 原有的返回值
            currentPage,
            features,
            activeFeature,
            notifications,
            logs,
            cronExpression,
            featureRunning,
            consoleLogs,
            categories,
            selectedCategory,
            filteredFeatures,
            customers,
            currentCustomer,
            filteredCategories,
            getCurrentClientName,
            currentUser,
            toggleCategory,
            selectCategory,
            openFeatureWindow,
            closeFeatureWindow,
            runFeature,
            stopFeature,
            removeNotification,
            saveCronJob,
            openAddCategoryModal,
            toggleCategoryEdite,
            categorieEditMode,
            modal,
            modalWindow,
            openModal,
            closeModal,
            logout,
            // 配置管理相关方法
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
        }
    }
}).component('sidebar-menu', SidebarMenu).mount('#app');