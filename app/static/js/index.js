
const { createApp, ref, computed, onMounted, provide } = Vue
import api from './api/api.js';
import SidebarMenu from './defineComponent.js';

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

        const currentCustomer = ref('')     // 当前客户
        const customers = ref([])           // 所有客户
        const categories = ref([])          // 所有分类
        const features = ref([]);           // 所有功能

        onMounted(async () => {
            // 获取所有功能
            let response = await api.feature.get_all_feature();
            features.value = response.data.data;
            // 获取所有客户
            response = await api.customer.get_all_customer();
            customers.value = response.data.data;
            // 获取所有分类
            response = await api.category.get_all_category();
            categories.value = response.data.data;
        })

        const logs = ref([
            { id: 1, message: '系统启动 - 2024-03-12 10:00:00' },
            { id: 2, message: '功能1执行成功 - 2024-03-12 10:05:00' },
            { id: 3, message: '定时任务更新 - 2024-03-12 10:10:00' },
        ])


        // 根据选择的客户筛选分类
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
            if(!requestBody.name){
                alert("请输入新分类的名称！");
                return
            }
            // todo 为了提升体验，应该让API返回新增的对象，然后插入到当前对象的子列表中。
            // 现在的做法是插入完成后刷新侧边栏，会导致侧边栏全部折叠
            let response = await api.category.add_category(requestBody);
            console.log(response)
            if (response.data.status) {
                // 刷新分类
                response = await api.category.get_all_category();
                categories.value = response.data.data;
                closeModal()
            } else {
                alert("插入分类失败：" + response.data.data)
            }
        }

        const delCategory = async (params) => {
            debugger;
            const requestBody = {
                id: params.id
            }
            // todo 删除成功，直接利用引用删除现有嵌套结构
            let response = await api.category.del_category(requestBody);
            console.log(response)
            if (response.data.status) {
                // 刷新分类
                response = await api.category.get_all_category();
                categories.value = response.data.data;
                closeModal()
            } else {
                alert("删除分类失败：" + response.data.data)
            }
        }
        // 打开新增分类窗口
        const openAddCategoryModal = (category, event) => {
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
                    label: "提交",
                    style: "",
                    function: addCategory,
                    param: category
                },
                {
                    label: "删除",
                    style: "",
                    function: delCategory,
                    param: category
                }
            ]
            const buttonElement = event.currentTarget;
            openModal("编辑分类", "填写数据点击新增，在当前分类下创建一个子分类；\<br\>点击删除，删除当前分类", fields, buttons, buttonElement)
        }

        const openModal = (title, description, fields, buttons, buttonElement) => {
            const rect = buttonElement.getBoundingClientRect();
            modal.value.top = rect.top + window.scrollY,
            modal.value.left = (rect.left + window.scrollX) * 1.25
            modal.value.show = true
            modal.value.title = title
            modal.value.fields = fields
            modal.value.description = description
            modal.value.buttons = buttons
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
            featureRunning.value = true
            addConsoleLog(`开始运行${activeFeature.value.name}...`, 'info')

            // 模拟WebSocket接收到的日志
            simulateConsoleOutput()

            // 添加通知
            addNotification(`${activeFeature.value.name}已开始运行`)
        }

        // 停止功能
        const stopFeature = () => {
            featureRunning.value = false
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
                    if (featureRunning.value) { // 只有在仍在运行时才添加日志
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

        provide('openAddCategoryModal', openAddCategoryModal);
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
            openModal,
            closeModal,
        }
    }
}).component('sidebar-menu', SidebarMenu).mount('#app');