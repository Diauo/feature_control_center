# 前端集成用户认证和权限控制设计

## 1. 前端架构概述

前端采用Vue.js框架，需要集成用户认证和权限控制功能，包括：
1. 用户登录/登出流程
2. JWT令牌管理
3. 基于角色的界面显示控制
4. 基于客户关联的数据显示控制
5. 权限不足时的友好提示

## 2. 认证状态管理

### 2.1 Vuex状态管理
创建专门的认证模块来管理用户状态：

```javascript
// store/auth.js
const state = {
  isAuthenticated: false,
  user: null,
  token: localStorage.getItem('access_token') || null,
  refreshToken: localStorage.getItem('refresh_token') || null
};

const mutations = {
  SET_AUTH(state, { user, token, refreshToken }) {
    state.isAuthenticated = true;
    state.user = user;
    state.token = token;
    state.refreshToken = refreshToken;
    localStorage.setItem('access_token', token);
    localStorage.setItem('refresh_token', refreshToken);
  },
  
  CLEAR_AUTH(state) {
    state.isAuthenticated = false;
    state.user = null;
    state.token = null;
    state.refreshToken = null;
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  },
  
  SET_USER(state, user) {
    state.user = user;
  }
};

const actions = {
  login({ commit }, { username, password }) {
    // 调用登录API
  },
  
  logout({ commit }) {
    // 调用登出API并清理状态
  },
  
  refreshTokens({ commit }) {
    // 刷新令牌
  }
};

const getters = {
  isAuthenticated: state => state.isAuthenticated,
  user: state => state.user,
  userRole: state => state.user ? state.user.role : null,
  token: state => state.token
};
```

## 3. 登录页面设计

### 3.1 登录表单组件
```vue
<!-- components/LoginForm.vue -->
<template>
  <div class="login-form">
    <h2>用户登录</h2>
    <form @submit.prevent="handleLogin">
      <div class="form-group">
        <label for="username">用户名</label>
        <input 
          type="text" 
          id="username" 
          v-model="username" 
          required 
          placeholder="请输入用户名"
        />
      </div>
      
      <div class="form-group">
        <label for="password">密码</label>
        <input 
          type="password" 
          id="password" 
          v-model="password" 
          required 
          placeholder="请输入密码"
        />
      </div>
      
      <button type="submit" :disabled="loading">
        {{ loading ? '登录中...' : '登录' }}
      </button>
      
      <div v-if="error" class="error-message">
        {{ error }}
      </div>
    </form>
  </div>
</template>

<script>
export default {
  data() {
    return {
      username: '',
      password: '',
      loading: false,
      error: ''
    };
  },
  
  methods: {
    async handleLogin() {
      this.loading = true;
      this.error = '';
      
      try {
        const response = await api.auth.login({
          username: this.username,
          password: this.password
        });
        
        if (response.data.status) {
          // 登录成功，存储令牌和用户信息
          this.$store.commit('auth/SET_AUTH', {
            user: response.data.data.user,
            token: response.data.data.access_token,
            refreshToken: response.data.data.refresh_token
          });
          
          // 跳转到主页
          this.$router.push('/');
        } else {
          this.error = response.data.data;
        }
      } catch (err) {
        this.error = '登录失败，请检查用户名和密码';
      } finally {
        this.loading = false;
      }
    }
  }
};
</script>
```

### 3.2 登录路由
```javascript
// router/index.js
import Login from '@/views/Login.vue';

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: Login,
    meta: { requiresGuest: true }
  },
  // 其他路由...
];
```

## 4. 路由权限控制

### 4.1 路由守卫
```javascript
// router/index.js
import store from '@/store';

router.beforeEach((to, from, next) => {
  const isAuthenticated = store.getters['auth/isAuthenticated'];
  
  // 需要认证的路由
  if (to.matched.some(record => record.meta.requiresAuth)) {
    if (!isAuthenticated) {
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      });
    } else {
      next();
    }
  }
  // 游客专用路由（如登录页）
  else if (to.matched.some(record => record.meta.requiresGuest)) {
    if (isAuthenticated) {
      next('/');
    } else {
      next();
    }
  }
  // 其他路由
  else {
    next();
  }
});
```

### 4.2 角色基础路由
```javascript
// router/index.js
const routes = [
  {
    path: '/',
    name: 'Home',
    component: Home,
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    name: 'Admin',
    component: Admin,
    meta: { requiresAuth: true, role: 'admin' }
  },
  {
    path: '/manager',
    name: 'Manager',
    component: Manager,
    meta: { requiresAuth: true, role: 'manager' }
  }
];
```

### 4.3 角色权限路由守卫
```javascript
router.beforeEach((to, from, next) => {
  const isAuthenticated = store.getters['auth/isAuthenticated'];
  const userRole = store.getters['auth/userRole'];
  
  // 检查是否需要认证
  if (to.matched.some(record => record.meta.requiresAuth)) {
    if (!isAuthenticated) {
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      });
    } else {
      // 检查角色权限
      const requiredRole = to.matched.find(record => record.meta.role)?.meta.role;
      if (requiredRole) {
        if (hasPermission(userRole, requiredRole)) {
          next();
        } else {
          next({ name: 'NotFound' }); // 或者跳转到无权限页面
        }
      } else {
        next();
      }
    }
  } else {
    next();
  }
});

// 权限检查函数
function hasPermission(userRole, requiredRole) {
  if (userRole === 'admin') return true; // 超级管理员拥有所有权限
  if (requiredRole === 'manager' && userRole === 'manager') return true;
  if (requiredRole === 'operator' && (userRole === 'operator' || userRole === 'manager')) return true;
  return false;
}
```

## 5. 界面权限控制

### 5.1 基于角色的元素显示
```vue
<!-- components/Navigation.vue -->
<template>
  <nav>
    <router-link to="/">首页</router-link>
    
    <!-- 仅管理员可见 -->
    <router-link 
      v-if="userRole === 'admin'" 
      to="/admin"
    >
      管理员面板
    </router-link>
    
    <!-- 管理员和客户经理可见 -->
    <router-link 
      v-if="userRole === 'admin' || userRole === 'manager'" 
      to="/manager"
    >
      客户经理面板
    </router-link>
    
    <!-- 所有认证用户可见 -->
    <a href="#" @click="logout">登出</a>
  </nav>
</template>

<script>
import { mapGetters } from 'vuex';

export default {
  computed: {
    ...mapGetters('auth', ['userRole'])
  },
  
  methods: {
    logout() {
      this.$store.dispatch('auth/logout');
      this.$router.push('/login');
    }
  }
};
</script>
```

### 5.2 基于客户关联的数据过滤
```vue
<!-- views/FeatureList.vue -->
<template>
  <div>
    <h2>功能列表</h2>
    
    <!-- 客户选择器（仅管理员和客户经理可见） -->
    <div 
      v-if="userRole === 'admin' || userRole === 'manager'" 
      class="customer-selector"
    >
      <label>选择客户：</label>
      <select v-model="selectedCustomer">
        <option value="">所有客户</option>
        <option 
          v-for="customer in associatedCustomers" 
          :key="customer.id" 
          :value="customer.id"
        >
          {{ customer.name }}
        </option>
      </select>
    </div>
    
    <!-- 功能列表 -->
    <div class="features-grid">
      <div 
        v-for="feature in filteredFeatures" 
        :key="feature.id" 
        class="feature-card"
      >
        <h3>{{ feature.name }}</h3>
        <p>{{ feature.description }}</p>
        
        <!-- 管理按钮（仅管理员和客户经理可见） -->
        <div 
          v-if="canManageFeature(feature)" 
          class="feature-actions"
        >
          <button @click="editFeature(feature)">编辑</button>
          <button @click="deleteFeature(feature)">删除</button>
        </div>
        
        <!-- 运行按钮（所有认证用户可见） -->
        <button 
          v-if="canExecuteFeature(feature)" 
          @click="runFeature(feature)"
        >
          运行
        </button>
      </div>
    </div>
  </div>
</template>

<script>
import { mapGetters } from 'vuex';

export default {
  data() {
    return {
      selectedCustomer: '',
      features: [],
      associatedCustomers: []
    };
  },
  
  computed: {
    ...mapGetters('auth', ['userRole', 'user']),
    
    filteredFeatures() {
      if (!this.selectedCustomer) return this.features;
      
      return this.features.filter(
        feature => feature.customer_id === parseInt(this.selectedCustomer)
      );
    }
  },
  
  async created() {
    // 获取功能列表
    await this.loadFeatures();
    
    // 获取关联客户（仅管理员和客户经理）
    if (this.userRole === 'admin' || this.userRole === 'manager') {
      await this.loadAssociatedCustomers();
    }
  },
  
  methods: {
    canManageFeature(feature) {
      // 管理员可以管理所有功能
      if (this.userRole === 'admin') return true;
      
      // 客户经理只能管理关联客户的功能
      if (this.userRole === 'manager') {
        return this.associatedCustomers.some(
          customer => customer.id === feature.customer_id
        );
      }
      
      return false;
    },
    
    canExecuteFeature(feature) {
      // 管理员可以执行所有功能
      if (this.userRole === 'admin') return true;
      
      // 客户经理和操作员只能执行关联客户的功能
      if (this.userRole === 'manager' || this.userRole === 'operator') {
        return this.associatedCustomers.some(
          customer => customer.id === feature.customer_id
        );
      }
      
      return false;
    },
    
    async loadFeatures() {
      // 根据用户角色加载不同的功能列表
      const response = await api.feature.get_all_feature();
      if (response.data.status) {
        this.features = response.data.data;
      }
    },
    
    async loadAssociatedCustomers() {
      // 获取当前用户关联的客户
      const response = await api.user.get_my_customers();
      if (response.data.status) {
        this.associatedCustomers = response.data.data;
      }
    }
  }
};
</script>
```

## 6. API集成

### 6.1 认证相关API
```javascript
// api/auth.js
import axios from 'axios';

export default {
  login(credentials) {
    return axios.post('/api/users/login', credentials);
  },
  
  register(userData) {
    return axios.post('/api/users/register', userData);
  },
  
  logout() {
    return axios.post('/api/users/logout');
  },
  
  refreshTokens(refreshToken) {
    return axios.post('/api/users/refresh', { refresh_token: refreshToken });
  },
  
  getCurrentUser() {
    return axios.get('/api/users/me');
  }
};
```

### 6.2 请求拦截器
```javascript
// api/index.js
import axios from 'axios';
import store from '@/store';

// 请求拦截器，自动添加JWT令牌
axios.interceptors.request.use(
  config => {
    const token = store.getters['auth/token'];
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  error => {
    return Promise.reject(error);
  }
);

// 响应拦截器，处理认证错误
axios.interceptors.response.use(
  response => {
    return response;
  },
  error => {
    if (error.response?.status === 401) {
      // 令牌过期或无效，尝试刷新令牌
      store.dispatch('auth/refreshTokens');
    }
    return Promise.reject(error);
  }
);
```

## 7. 权限不足处理

### 7.1 无权限页面
```vue
<!-- views/NoPermission.vue -->
<template>
  <div class="no-permission">
    <h1>权限不足</h1>
    <p>您没有访问此页面的权限。</p>
    <router-link to="/">返回首页</router-link>
  </div>
</template>

<style scoped>
.no-permission {
  text-align: center;
  padding: 2rem;
}

.no-permission h1 {
  color: #e74c3c;
  margin-bottom: 1rem;
}
</style>
```

### 7.2 通知系统集成
```javascript
// utils/notifications.js
export function showPermissionDenied() {
  // 显示权限不足的通知
  // 可以集成到现有的通知系统中
}
```

## 8. 用户界面优化

### 8.1 用户信息显示
```vue
<!-- components/UserInfo.vue -->
<template>
  <div class="user-info">
    <span>欢迎，{{ user.username }}</span>
    <span class="user-role">({{ roleDisplayName }})</span>
    <button @click="logout">登出</button>
  </div>
</template>

<script>
import { mapGetters } from 'vuex';

export default {
  computed: {
    ...mapGetters('auth', ['user']),
    
    roleDisplayName() {
      const roles = {
        'admin': '超级管理员',
        'manager': '客户经理',
        'operator': '操作员'
      };
      return roles[this.user.role] || this.user.role;
    }
  },
  
  methods: {
    logout() {
      this.$store.dispatch('auth/logout');
      this.$router.push('/login');
    }
  }
};
</script>
```

## 9. 安全考虑

### 9.1 令牌存储
1. 访问令牌存储在内存中（Vuex状态）
2. 刷新令牌存储在HttpOnly Cookie中或localStorage中（需要权衡安全性与实现复杂度）
3. 页面刷新时从存储中恢复令牌

### 9.2 XSS防护
1. 避免在模板中直接输出用户输入
2. 使用Vue的内置转义机制
3. 对用户输入进行验证和清理

### 9.3 CSRF防护
1. 使用JWT令牌而非Cookie进行认证
2. 确保API端点有适当的权限验证

## 10. 性能优化

### 10.1 权限缓存
1. 缓存用户角色和关联客户信息
2. 减少重复的API调用
3. 在用户登录时一次性获取所需信息

### 10.2 懒加载
1. 根据用户角色动态加载路由组件
2. 按需加载权限相关的组件