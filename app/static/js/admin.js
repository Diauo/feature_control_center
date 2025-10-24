const { createApp, ref, onMounted } = Vue;
import authService from './services/authService.js';
import { useAuth } from './composables/useAuth.js';
import { useModal } from './composables/useModal.js';
import api from './api/api.js';

createApp({
    setup() {
        const currentUser = ref(null);
        const { logout } = useAuth(authService, api);
        const { modal, modalWindow, openModal, closeModal } = useModal();
        const currentPage = ref('users');
        const users = ref([]);
        const customers = ref([]);

        const loadUsers = async () => {
            try {
                const response = await api.user.getUsers();
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
                const response = await api.customer.get_all_customer();
                if (response.data.status) {
                    customers.value = response.data.data;
                } else {
                    alert('加载客户列表失败: ' + response.data.message);
                }
            } catch (error) {
                alert('加载客户列表时出错: ' + error);
            }
        };

        const saveUser = async () => {
            const userData = { ...modal.value.modalParams };
            const isEdit = userData.id !== undefined;

            if (isEdit && !userData.password) {
                delete userData.password;
            }
            
            // 如果角色是管理员，确保不关联任何客户
            if (userData.role === 'admin') {
                userData.associated_customers = [];
            }

            try {
                let response;
                if (isEdit) {
                    response = await api.user.updateUser(userData);
                } else {
                    response = await api.user.createUser(userData);
                }

                if (response.data.status) {
                    closeModal();
                    await loadUsers();
                } else {
                    alert('保存用户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('保存用户时出错: ' + error);
            }
        };

        const openUserModal = (user = null, event) => {
            const isEdit = user !== null;
            const title = isEdit ? '编辑用户' : '新增用户';
            
            modal.value.modalParams = {
                id: user ? user.id : undefined,
                username: user ? user.username : '',
                email: user ? user.email : '',
                password: '',
                role: user ? user.role : 'operator',
                associated_customers: user && user.customers ? user.customers.map(c => c.id) : []
            };
            debugger;
            const fields = [
                { key: 'username', label: '用户名', type: 'text' },
                { key: 'email', label: '邮箱', type: 'text' },
                { key: 'password', label: '密码', type: 'password', placeholder: isEdit ? '留空则不修改' : '必填' },
                {
                    key: 'role',
                    label: '角色',
                    type: 'select',
                    options: [
                        { value: 'operator', text: 'Operator' },
                        { value: 'admin', text: 'Admin' }
                    ]
                },
                {
                    key: 'associated_customers',
                    label: '关联客户',
                    type: 'multiselect',
                    options: customers.value.map(c => ({ value: c.id, text: c.name })),
                }
            ];

            const buttons = [
                { label: '保存', style: 'btn-primary', function: saveUser }
            ];

            openModal(title, '', fields, buttons, event.target);
        };

        const deleteUser = async (userId) => {
            if (!confirm('确定要删除此用户吗？')) {
                return;
            }

            try {
                const response = await api.user.deleteUser(userId);
                if (response.data.status) {
                    await loadUsers();
                } else {
                    alert('删除用户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('删除用户时出错: ' + error);
            }
        };

        const saveCustomer = async () => {
            const customerData = { ...modal.value.modalParams };
            const isEdit = customerData.id !== undefined;

            try {
                let response;
                if (isEdit) {
                    response = await api.customer.update_customer(customerData);
                } else {
                    response = await api.customer.add_customer(customerData);
                }

                if (response.data.status) {
                    closeModal();
                    await loadCustomers();
                } else {
                    alert('保存客户失败: ' + response.data.message);
                }
            } catch (error) {
                alert('保存客户时出错: ' + error);
            }
        };

        const openCustomerModal = (customer = null, event) => {
            const isEdit = customer !== null;
            const title = isEdit ? '编辑客户' : '新增客户';

            modal.value.modalParams = {
                id: customer ? customer.id : undefined,
                name: customer ? customer.name : '',
                description: customer ? customer.description : ''
            };

            const fields = [
                { key: 'name', label: '客户名称', type: 'text' },
                { key: 'description', label: '描述', type: 'textarea' }
            ];

            const buttons = [
                { label: '保存', style: 'btn-primary', function: saveCustomer }
            ];

            openModal(title, '', fields, buttons, event.target);
        };

        const deleteCustomer = async (customerId) => {
            if (!confirm('确定要删除此客户吗？')) {
                return;
            }

            try {
                const response = await api.customer.del_customer(customerId);
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
            if (!authService.isAuthenticated()) {
                window.location.href = '/login';
                return;
            }
            if (authService.isTokenExpired()) {
                const refreshSuccess = await authService.refreshAccessToken();
                if (!refreshSuccess) {
                    window.location.href = '/login';
                    return;
                }
            }
            currentUser.value = authService.getCurrentUser();
            if (!currentUser.value || currentUser.value.role !== 'admin') {
                alert('您没有权限访问此页面。');
                window.location.href = '/';
                return;
            }
            await loadCustomers();
            await loadUsers();
        });

        return {
            currentUser,
            logout,
            modal,
            modalWindow,
            openModal,
            closeModal,
            currentPage,
            users,
            customers,
            openUserModal,
            deleteUser,
            openCustomerModal,
            deleteCustomer
        };
    }
}).mount('#app');