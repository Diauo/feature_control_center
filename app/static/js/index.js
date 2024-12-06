
const { createApp, ref, computed } = Vue

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

        // 示例分类数据
        const categories = ref([
            {
                id: 1,
                name: 'Shopify平台',
                expanded: true,
                items: [
                    { id: 'shopify-order', name: '订单管理' },
                    { id: 'shopify-product', name: '商品管理' },
                ]
            },
            {
                id: 2,
                name: 'OZON平台',
                expanded: false,
                items: [
                    { id: 'ozon-inventory', name: '库存同步' },
                    { id: 'ozon-price', name: '价格更新' },
                ]
            },
            {
                id: 3,
                name: 'ERP系统',
                expanded: false,
                items: [
                    { id: 'erp-sync', name: '数据同步' },
                    { id: 'erp-report', name: '报表生成' },
                ]
            }
        ])

        const features = ref([
            {
                id: 1,
                name: '订单同步',
                description: '从Shopify平台同步最新订单到ME3系统',
                category: 'shopify-order',
                clientId: 'client-a'
            },
            {
                id: 2,
                name: '库存同步',
                description: '将ME3系统的库存同步到shopify',
                category: 'shopify-product',
                clientId: 'client-a'
            },
            {
                id: 3,
                name: '商品更新',
                description: '从ME3系统获取数据更新Shopify平台商品信息',
                category: 'shopify-product',
                clientId: 'client-a'
            },
            {
                id: 4,
                name: 'OZON库存同步',
                description: '将ME3系统的库存同步到OZON',
                category: 'ozon-inventory',
                clientId: 'client-b'
            },
            {
                id: 4,
                name: 'OZON价格更新',
                description: '批量更新OZON平台商品价格',
                category: 'ozon-price',
                clientId: 'client-b'
            },
            {
                id: 5,
                name: 'ERP数据同步',
                description: '同步ERP系统数据',
                category: 'erp-sync',
                clientId: 'client-c'
            },
            {
                id: 6,
                name: '月度报表',
                description: '生成系统月度运营报表',
                category: 'erp-report',
                clientId: 'client-c'
            }
        ]);

        const logs = ref([
            { id: 1, message: '系统启动 - 2024-03-12 10:00:00' },
            { id: 2, message: '功能1执行成功 - 2024-03-12 10:05:00' },
            { id: 3, message: '定时任务更新 - 2024-03-12 10:10:00' },
        ])

        // // 根据选择的类别过滤功能
        // const filteredFeatures = computed(() => {
        //     if (!selectedCategory.value) {
        //         return features.value
        //     }
        //     return features.value.filter(feature => feature.category === selectedCategory.value)
        // })

        // 根据选择的客户筛选分类
        const filteredCategories = computed(() => {
            if (!selectedClient.value) {
                return categories.value
            }
            return categories.value.filter(category =>
                category.clientId === selectedClient.value
            )
        })

        // 根据选择的客户和分类筛选功能
        const filteredFeatures = computed(() => {
            let result = features.value

            if (selectedClient.value) {
                result = result.filter(feature =>
                    feature.clientId === selectedClient.value
                )
            }
            if (selectedCategory.value) {
                result = result.filter(feature =>
                    feature.category === selectedCategory.value
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
        const selectCategory = (categoryId) => {
            selectedCategory.value = categoryId
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