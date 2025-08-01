/**
 * 认证服务
 * 处理JWT令牌的存储、刷新和认证检查
 */

class AuthService {
    /**
     * 获取访问令牌
     * @returns {string|null}
     */
    getAccessToken() {
        return localStorage.getItem('access_token');
    }

    /**
     * 获取刷新令牌
     * @returns {string|null}
     */
    getRefreshToken() {
        return localStorage.getItem('refresh_token');
    }

    /**
     * 获取当前用户信息
     * @returns {Object|null}
     */
    getCurrentUser() {
        const user = localStorage.getItem('user');
        return user ? JSON.parse(user) : null;
    }

    /**
     * 存储令牌和用户信息
     * @param {string} accessToken 
     * @param {string} refreshToken 
     * @param {Object} user 
     */
    setTokens(accessToken, refreshToken, user) {
        localStorage.setItem('access_token', accessToken);
        localStorage.setItem('refresh_token', refreshToken);
        localStorage.setItem('user', JSON.stringify(user));
    }

    /**
     * 清除令牌和用户信息
     */
    clearTokens() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
    }

    /**
     * 检查用户是否已认证
     * @returns {boolean}
     */
    isAuthenticated() {
        return !!this.getAccessToken();
    }

    /**
     * 刷新访问令牌
     * @returns {Promise<boolean>} 刷新是否成功
     */
    async refreshAccessToken() {
        const refreshToken = this.getRefreshToken();
        if (!refreshToken) {
            return false;
        }

        try {
            // 导入api模块（需要动态导入以避免循环依赖）
            const apiModule = await import('../api/api.js');
            const api = apiModule.default;
            
            const response = await api.user.refreshTokens(refreshToken);
            if (response.data.status) {
                const { access_token } = response.data.data;
                localStorage.setItem('access_token', access_token);
                return true;
            }
        } catch (error) {
            console.error('Token refresh failed:', error);
        }
        
        // 刷新失败，清除令牌
        this.clearTokens();
        return false;
    }

    /**
     * 检查访问令牌是否过期
     * @returns {boolean}
     */
    isTokenExpired() {
        const token = this.getAccessToken();
        if (!token) return true;

        try {
            const payload = JSON.parse(atob(token.split('.')[1]));
            const currentTime = Math.floor(Date.now() / 1000);
            return payload.exp < currentTime;
        } catch (error) {
            console.error('Token parsing error:', error);
            return true;
        }
    }
}

// 导出单例实例
export default new AuthService();