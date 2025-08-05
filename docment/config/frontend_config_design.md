# 前端配置管理页面设计

## 页面功能需求
1. 显示所有配置项列表
2. 支持新增配置项
3. 支持编辑配置项
4. 支持删除配置项（需要确认）
5. 支持配置重载
6. 支持清理无效配置
7. 配置项包括：名称、值、默认值、描述、关联功能ID

## 页面布局设计

### 主要组件
1. 配置列表表格
2. 新增/编辑配置模态框
3. 操作按钮区域

### 页面结构
```html
<div id="config-management">
  <!-- 操作按钮区域 -->
  <div class="config-actions">
    <button class="btn-primary" @click="openAddConfigModal">新增配置</button>
    <button class="btn-secondary" @click="reloadConfig">重载配置</button>
    <button class="btn-warning" @click="cleanupConfig">清理无效配置</button>
  </div>
  
  <!-- 配置列表 -->
  <div class="config-list">
    <table class="config-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>名称</th>
          <th>值</th>
          <th>默认值</th>
          <th>描述</th>
          <th>关联功能ID</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="config in configs" :key="config.id">
          <td>{{ config.id }}</td>
          <td>{{ config.name }}</td>
          <td>{{ config.value }}</td>
          <td>{{ config.default_value }}</td>
          <td>{{ config.description }}</td>
          <td>{{ config.feature_id }}</td>
          <td>
            <button class="btn-edit" @click="openEditConfigModal(config)">编辑</button>
            <button class="btn-danger" @click="deleteConfig(config)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  
  <!-- 新增/编辑配置模态框 -->
  <div class="modal" v-if="showConfigModal">
    <div class="modal-content">
      <h3>{{ modalTitle }}</h3>
      <form @submit.prevent="saveConfig">
        <div class="form-group">
          <label>名称:</label>
          <input type="text" v-model="currentConfig.name" required>
        </div>
        <div class="form-group">
          <label>值:</label>
          <input type="text" v-model="currentConfig.value">
        </div>
        <div class="form-group">
          <label>默认值:</label>
          <input type="text" v-model="currentConfig.default_value">
        </div>
        <div class="form-group">
          <label>描述:</label>
          <textarea v-model="currentConfig.description"></textarea>
        </div>
        <div class="form-group">
          <label>关联功能ID:</label>
          <input type="number" v-model="currentConfig.feature_id" min="0">
        </div>
        <div class="form-actions">
          <button type="submit" class="btn-primary">保存</button>
          <button type="button" class="btn-secondary" @click="closeConfigModal">取消</button>
        </div>
      </form>
    </div>
  </div>
</div>
```

## Vue组件设计

### 组件数据结构
```javascript
data() {
  return {
    configs: [], // 配置列表
    showConfigModal: false, // 是否显示配置模态框
    isEditing: false, // 是否为编辑模式
    currentConfig: {
      id: null,
      name: '',
      value: '',
      default_value: '',
      description: '',
      feature_id: 0
    }
  }
}
```

### 组件方法
```javascript
methods: {
  // 获取所有配置
  async loadConfigs() {
    try {
      const response = await api.config.get_all_config();
      this.configs = response.data.data;
    } catch (error) {
      console.error('获取配置列表失败:', error);
      // 显示错误提示
    }
  },
  
  // 打开新增配置模态框
  openAddConfigModal() {
    this.isEditing = false;
    this.currentConfig = {
      id: null,
      name: '',
      value: '',
      default_value: '',
      description: '',
      feature_id: 0
    };
    this.showConfigModal = true;
  },
  
  // 打开编辑配置模态框
  openEditConfigModal(config) {
    this.isEditing = true;
    this.currentConfig = { ...config };
    this.showConfigModal = true;
  },
  
  // 关闭配置模态框
  closeConfigModal() {
    this.showConfigModal = false;
  },
  
  // 保存配置
  async saveConfig() {
    try {
      if (this.isEditing) {
        // 更新配置
        await api.config.update_config(this.currentConfig.id, this.currentConfig);
      } else {
        // 新增配置
        await api.config.add_config(this.currentConfig);
      }
      // 关闭模态框
      this.closeConfigModal();
      // 重新加载配置列表
      await this.loadConfigs();
      // 显示成功提示
    } catch (error) {
      console.error('保存配置失败:', error);
      // 显示错误提示
    }
  },
  
  // 删除配置
  async deleteConfig(config) {
    if (confirm(`确定要删除配置 "${config.name}" 吗？`)) {
      try {
        await api.config.delete_config(config.id);
        // 重新加载配置列表
        await this.loadConfigs();
        // 显示成功提示
      } catch (error) {
        console.error('删除配置失败:', error);
        // 显示错误提示
      }
    }
  },
  
  // 重载配置
  async reloadConfig() {
    try {
      await api.config.reload();
      // 显示成功提示
    } catch (error) {
      console.error('重载配置失败:', error);
      // 显示错误提示
    }
  },
  
  // 清理无效配置
  async cleanupConfig() {
    if (confirm('确定要清理无效配置吗？')) {
      try {
        const response = await api.config.cleanup();
        // 显示清理结果
        // 重新加载配置列表
        await this.loadConfigs();
      } catch (error) {
        console.error('清理配置失败:', error);
        // 显示错误提示
      }
    }
  }
}
```

## 样式设计
```css
.config-actions {
  margin-bottom: 20px;
}

.config-actions button {
  margin-right: 10px;
}

.config-table {
  width: 100%;
  border-collapse: collapse;
}

.config-table th,
.config-table td {
  border: 1px solid #ddd;
  padding: 8px;
  text-align: left;
}

.config-table th {
  background-color: #f2f2f2;
}

.btn-edit {
  background-color: #ffc107;
  color: #000;
  border: none;
  padding: 5px 10px;
  margin-right: 5px;
  cursor: pointer;
}

.btn-danger {
  background-color: #dc3545;
  color: white;
  border: none;
  padding: 5px 10px;
  cursor: pointer;
}

.modal {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0,0,0,0.5);
  display: flex;
  justify-content: center;
  align-items: center;
}

.modal-content {
  background-color: white;
  padding: 20px;
  border-radius: 5px;
  width: 500px;
}

.form-group {
  margin-bottom: 15px;
}

.form-group label {
  display: block;
  margin-bottom: 5px;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.form-actions {
  text-align: right;
}