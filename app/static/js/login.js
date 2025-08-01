const { createApp, ref, onMounted } = Vue;
import api from './api/api.js';

const app = createApp({
    setup() {
        const loginForm = ref({
            username: '',
            password: ''
        });
        
        const loading = ref(false);
        const errorMessage = ref('');
        
        // 检查是否已经登录
        onMounted(() => {
            const token = localStorage.getItem('access_token');
            if (token) {
                // 如果已经有token，重定向到主页面
                window.location.href = '/';
            }
        });
        
        // 处理登录
        const handleLogin = async () => {
            if (!loginForm.value.username || !loginForm.value.password) {
                errorMessage.value = '请输入用户名和密码';
                return;
            }
            
            loading.value = true;
            errorMessage.value = '';
            
            try {
                const response = await api.user.login({
                    username: loginForm.value.username,
                    password: loginForm.value.password
                });
                
                if (response.data.status) {
                    // 存储令牌和用户信息
                    const { access_token, refresh_token, user } = response.data.data;
                    localStorage.setItem('access_token', access_token);
                    localStorage.setItem('refresh_token', refresh_token);
                    localStorage.setItem('user', JSON.stringify(user));
                    
                    // 重定向到主页面
                    window.location.href = '/';
                } else {
                    errorMessage.value = response.data.data || '登录失败';
                }
            } catch (error) {
                console.error('Login error:', error);
                if (error.response && error.response.data) {
                    errorMessage.value = error.response.data.data || '登录失败';
                } else {
                    errorMessage.value = '网络错误，请稍后重试';
                }
            } finally {
                loading.value = false;
            }
        };
        
        return {
            loginForm,
            loading,
            errorMessage,
            handleLogin
        };
    }
});

app.mount('#app');