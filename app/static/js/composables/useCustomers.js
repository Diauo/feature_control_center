const { ref, computed } = Vue;

export function useCustomers() {
    const currentCustomer = ref('');
    const customers = ref([]);

    // 获取当前客户名称
    const getCurrentClientName = computed(() => {
        if (!currentCustomer.value) return '';
        const client = customers.value.find(c => c.id === currentCustomer.value);
        return client ? client.name : '';
    });

    // 加载所有客户 - 需要在调用时传入 api 和 addNotification
    const loadCustomers = async (api, addNotification) => {
        try {
            const response = await api.customer.get_all_customer();
            if (response.data.status) {
                customers.value = response.data.data;
                
                // 如果有客户，选择第一个客户作为默认客户
                if (customers.value.length > 0) {
                    currentCustomer.value = customers.value[0].id;
                }
                return { success: true };
            } else {
                addNotification(response.data.message || '加载客户列表失败');
                return { success: false, error: response.data.message };
            }
        } catch (error) {
            console.error('加载客户失败:', error);
            addNotification('加载客户时发生错误: ' + error.message);
            return { success: false, error };
        }
    };

    return {
        currentCustomer,
        customers,
        getCurrentClientName,
        loadCustomers
    };
}