
const { createApp, ref, computed, onMounted } = Vue

createApp({
    setup() {
        const currentPage = ref('home')
        const activeFeature = ref(null)
        const notifications = ref([])
        const cronExpression = ref('')
        const notificationCount = ref(0)
        const isRunning = ref(false)
        const consoleLogs = ref([])
        const selectedCategory = ref(null)

        const selectedClient = ref('')
        const clients = ref([
            { id: 'client-a', name: 'shopify公司' },
            { id: 'client-b', name: 'ozon公司' },
            { id: 'client-c', name: 'ME3公司' },
        ])
        
        // 加载完成后获取后端数据
        const features = ref([]);

        onMounted(async()=>{
            debugger;
            const response = await window.api.get_all_feature();
            features.value = response.data.data;
        })

        // 示例分类数据
        const categories = ref([
            {
                order_id: 1,
                name: 'Shopify平台',
                code: 'shopify',
                expanded: true,
            },
            {
                order_id: 2,
                name: 'OZON平台',
                code: 'ozon',
                expanded: false,
            },
            {
                order_id: 3,
                name: 'ERP系统',
                code: 'erp',
                expanded: false,
            }
        ])


        const logs = ref([
            { id: 1, message: '系统启动 - 2024-03-12 10:00:00' },
            { id: 2, message: '功能1执行成功 - 2024-03-12 10:05:00' },
            { id: 3, message: '定时任务更新 - 2024-03-12 10:10:00' },
        ])


        // 根据选择的客户筛选分类
        const filteredCategories = computed(() => {
            if (!selectedClient.value) {
                return categories.value
            }
            return categories.value.filter(category =>
                category.customer_id === selectedClient.value
            )
        })

        // 根据选择的客户和分类筛选功能
        const filteredFeatures = computed(() => {
            debugger;
            let result = features.value

            if (selectedClient.value) {
                result = result.filter(feature =>
                    feature.customer_id === selectedClient.value
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
            if (!selectedClient.value) return ''
            const client = clients.value.find(c => c.id === selectedClient.value)
            return client ? client.name : ''
        })

        // 切换分类展开/收起
        const toggleCategory = (category) => {
            category.expanded = !category.expanded
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
            if (isRunning.value) {
                if (confirm('功能正在运行中，确定要关闭窗口吗？')) {
                    stopFeature()
                } else {
                    return
                }
            }
            activeFeature.value = null
            isRunning.value = false
            consoleLogs.value = []
        }

        // 运行功能
        const runFeature = () => {
            isRunning.value = true
            addConsoleLog(`开始运行${activeFeature.value.name}...`, 'info')

            // 模拟WebSocket接收到的日志
            simulateConsoleOutput()

            // 添加通知
            addNotification(`${activeFeature.value.name}已开始运行`)
        }

        // 停止功能
        const stopFeature = () => {
            isRunning.value = false
            addConsoleLog('功能运行已终止', 'warning')
            addNotification(`${activeFeature.value.name}已停止运行`)
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
                    if (isRunning.value) { // 只有在仍在运行时才添加日志
                        addConsoleLog(msg, type)
                    }
                }, delay)
            })
        }

        // 添加通知
        const addNotification = (message) => {
            const id = notificationCount.value++
            notifications.value.push({
                id,
                message
            })
            // 10秒后自动移除通知
            setTimeout(() => {
                removeNotification(id)
            }, 10000)
        }

        // 移除通知
        const removeNotification = (id) => {
            const index = notifications.value.findIndex(n => n.id === id)
            if (index !== -1) {
                notifications.value.splice(index, 1)
            }
        }

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
        //         } else if (data.type === 'console' && isRunning.value) {
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

        return {
            // 原有的返回值
            currentPage,
            features,
            activeFeature,
            notifications,
            logs,
            cronExpression,
            isRunning,
            consoleLogs,
            categories,
            selectedCategory,
            filteredFeatures,
            clients,
            selectedClient,
            filteredCategories,
            getCurrentClientName,
            toggleCategory,
            selectCategory,
            openFeatureWindow,
            closeFeatureWindow,
            runFeature,
            stopFeature,
            removeNotification,
            saveCronJob
        }
    },
}).mount('#app')