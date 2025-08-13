export function useAuth(authService, api) {
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

    return {
        logout
    };
}