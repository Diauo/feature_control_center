const { createApp, ref, onMounted } = Vue;
import authService from './services/authService.js';
import { useAuth } from './composables/useAuth.js';
import api from './api/api.js';

createApp({
    setup() {
        const currentUser = ref(null);
        const { logout } = useAuth(authService, api);
        const currentPage = ref('users');
        const users = ref([]);
        const customers = ref([]);

        const userModal = ref({
            show: false,
            isEdit: false,
            data: {}
        });

        const customerModal = ref({
            show: false,
            isEdit: false,
            data: {}
        });

        const loadUsers = async () => {
            try {
                const response = await api.user.list_users();
                if (response.data.status) {
                    users.value = response.data.data.items;
                } else {
                    alert('加载用户列表失败: ' + response.data.message);
                }
            } catch (error) {
                alert('加载用户列表时出错: ' + error);
            }
        };

        const loadCustomers = async () => {
            try {
                const response = await api.customer.get_customers();
                if (response.data.status) {
                    customers.value = response.data.data;
                } else {
                    alert('加载客户列表失败: ' + response.data.message);
                }
            } catch (error) {
                alert('加载客户列表时出错: ' + error);
            }
        };

        const openUserModal = (user = null) => {
            if (user) {
                userModal.value.isEdit = true;
                userModal.value.data = { ...user, password: '', associated_customers: user.customers.map(c => c.id) };
            } else {
                userModal.value.isEdit = false;
                userModal.value.data = { username: '', email: '', password: '', role: 'operator', associated_customers: [] };
            }
            userModal.value.show = true;
        };

        const closeUserModal = () => {
            userModal.value.show = false;
        };

        const saveUser = async () => {
            const userData = { ...userModal.value.data };
            if (userModal.value.isEdit && !userData.password) {
                delete userData.password;
            }

            try {
                let response;
                if (userModal.value.isEdit) {
                    response = await api.user.update_user(userData.id, userData);
                } else {
                    response = await api.user.create_user(userData);
                }

                if (response.data.status) {
                    closeUserModal();
                    await loadUsers();
                } else {
                    alert('保存用户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('保存用户时出错: ' + error);
            }
        };

        const deleteUser = async (userId) => {
            if (!confirm('确定要删除此用户吗？')) {
                return;
            }

            try {
                const response = await api.user.delete_user(userId);
                if (response.data.status) {
                    await loadUsers();
                } else {
                    alert('删除用户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('删除用户时出错: ' + error);
            }
        };

        const openCustomerModal = (customer = null) => {
            if (customer) {
                customerModal.value.isEdit = true;
                customerModal.value.data = { ...customer };
            } else {
                customerModal.value.isEdit = false;
                customerModal.value.data = { name: '', description: '' };
            }
            customerModal.value.show = true;
        };

        const closeCustomerModal = () => {
            customerModal.value.show = false;
        };

        const saveCustomer = async () => {
            const customerData = { ...customerModal.value.data };

            try {
                let response;
                if (customerModal.value.isEdit) {
                    response = await api.customer.update_customer(customerData);
                } else {
                    response = await api.customer.add_customer(customerData);
                }

                if (response.data.status) {
                    closeCustomerModal();
                    await loadCustomers();
                } else {
                    alert('保存客户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('保存客户时出错: ' + error);
            }
        };

        const deleteCustomer = async (customerId) => {
            if (!confirm('确定要删除此客户吗？')) {
                return;
            }

            try {
                const response = await api.customer.del_customer({ id: customerId });
                if (response.data.status) {
                    await loadCustomers();
                } else {
                    alert('删除客户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('删除客户时出错: ' + error);
            }
        };

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

            // 验证用户角色
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                alert('您没有权限访问此页面。');
                window.location.href = '/';
                return;
            }

            await loadUsers();
            await loadCustomers();
        });

        return {
            currentUser,
            logout,
            currentPage,
            users,
            customers,
            userModal,
            openUserModal,
            closeUserModal,
            saveUser,
            deleteUser,
            customerModal,
            openCustomerModal,
            closeCustomerModal,
            saveCustomer,
            deleteCustomer
        };
    }
}).mount('#app');