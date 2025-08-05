# 错误处理和权限控制设计

## 后端错误处理

### 1. 统一错误响应格式
在配置控制器中使用统一的错误响应格式：

```python
def format_error_response(message, code=500):
    """格式化错误响应数据"""
    return jsonify({
        "status": False,
        "code": code,
        "data": message
    }), code
```

### 2. 控制器中的错误处理
在每个控制器方法中添加适当的错误处理：

```python
@config_bp.route('/get_all_config', methods=['GET'])
@require_role('admin')
def get_all_config():
    """获取所有配置"""
    try:
        status, msg, data = config_service.get_all_config()
        if not status:
            return format_error_response(msg, 500)
        else:
            return jsonify(data), 200
    except Exception as e:
        return format_error_response(f"获取配置列表失败: {str(e)}", 500)
```

### 3. 服务层错误处理
在服务层方法中添加适当的错误处理和日志记录：

```python
import logging

def get_all_config():
    try:
        sql = text('''
            select * from base_config
        ''')
        result = db.session.execute(sql).fetchall()
        return True, "成功", model_to_dict(result, Config)
    except Exception as e:
        logging.error(f"获取配置列表失败: {str(e)}")
        return False, f"获取配置列表失败: {str(e)}", []

def add_config(config):
    try:
        db.session.add(config)
        db.session.commit()
        return True, "添加成功", config.to_dict()
    except Exception as e:
        db.session.rollback()
        logging.error(f"添加配置失败: {str(e)}")
        return False, f"添加配置失败: {str(e)}", None
```

## 权限控制

### 1. 角色权限设计
系统中包含以下角色：
- `admin`: 管理员，拥有所有权限
- `manager`: 客户经理，拥有部分管理权限
- `operator`: 操作员，拥有基本操作权限

配置管理功能只允许管理员访问。

### 2. 权限装饰器使用
在所有配置管理API上使用`@require_role('admin')`装饰器：

```python
@config_bp.route('/add_config', methods=['POST'])
@require_role('admin')
def add_config():
    # 实现代码
    pass
```

### 3. 前端权限控制
在前端页面中，根据用户角色显示或隐藏相关功能：

```javascript
// 在Vue组件中
computed: {
  // 检查用户是否为管理员
  isAdmin() {
    return this.currentUser && this.currentUser.role === 'admin';
  }
}

// 在模板中
<div v-if="isAdmin" class="config-actions">
  <button class="btn-primary" @click="openAddConfigModal">新增配置</button>
  <button class="btn-secondary" @click="reloadConfig">重载配置</button>
  <button class="btn-warning" @click="cleanupConfig">清理无效配置</button>
</div>
```

## 前端错误处理

### 1. API调用错误处理
在每个API调用中添加错误处理：

```javascript
async loadConfigs() {
  try {
    const response = await api.config.get_all_config();
    if (response.data.status) {
      this.configs = response.data.data;
    } else {
      // 处理业务错误
      console.error('获取配置列表失败:', response.data.data);
      // 显示错误提示给用户
    }
  } catch (error) {
    // 处理网络错误或其他异常
    console.error('获取配置列表失败:', error);
    // 显示错误提示给用户
  }
}
```

### 2. 表单验证
在前端添加表单验证，确保用户输入的数据符合要求：

```javascript
methods: {
  validateConfig(config) {
    if (!config.name || config.name.trim() === '') {
      return '配置名称不能为空';
    }
    
    if (config.feature_id < 0) {
      return '关联功能ID不能为负数';
    }
    
    return null; // 验证通过
  },
  
  async saveConfig() {
    // 表单验证
    const errorMessage = this.validateConfig(this.currentConfig);
    if (errorMessage) {
      // 显示错误提示
      return;
    }
    
    try {
      // 保存配置
    } catch (error) {
      // 错误处理
    }
  }
}
```

## 日志记录

### 1. 后端日志记录
在关键操作中添加日志记录：

```python
import logging

def add_config(config):
    try:
        db.session.add(config)
        db.session.commit()
        logging.info(f"成功添加配置: {config.name}")
        return True, "添加成功", config.to_dict()
    except Exception as e:
        db.session.rollback()
        logging.error(f"添加配置失败: {str(e)}")
        return False, f"添加配置失败: {str(e)}", None
```

### 2. 前端日志记录
在关键操作中添加前端日志：

```javascript
async saveConfig() {
  try {
    // 保存配置
    console.log('配置保存成功:', this.currentConfig);
  } catch (error) {
    console.error('配置保存失败:', error);
  }
}
```

## 安全考虑

### 1. 输入验证
在后端对所有用户输入进行验证和清理：

```python
def validate_config_data(data):
    """验证配置数据"""
    if not data.get('name'):
        return False, "配置名称不能为空"
    
    if 'feature_id' in data and (not isinstance(data['feature_id'], int) or data['feature_id'] < 0):
        return False, "关联功能ID必须是非负整数"
    
    return True, "验证通过"

@config_bp.route('/add_config', methods=['POST'])
@require_role('admin')
def add_config():
    """新增配置"""
    request_body = request.get_json()
    if request_body is None:
        return "没有有效的参数", 400
    
    # 验证数据
    is_valid, message = validate_config_data(request_body)
    if not is_valid:
        return message, 400
    
    # 创建配置对象
    config = Config(**request_body)
    
    # 调用服务层添加配置
    status, msg, data = config_service.add_config(config)
    if not status:
        return msg, 500
    else:
        return format_response(True, data), 200
```

### 2. SQL注入防护
使用参数化查询来防止SQL注入：

```python
def get_config_by_id(config_id):
    if config_id is None:
        return False, "config_id为空", []
    # 使用参数化查询
    sql = text('''
        select * from base_config where id = :config_id
    ''')
    result = db.session.execute(sql, {'config_id': config_id}).fetchall()
    return True, "成功", model_to_dict(result, Config)
```

### 3. XSS防护
在前端正确转义用户输入的内容：

```javascript
// 在Vue模板中使用v-text而不是v-html来显示用户输入的内容
<td v-text="config.name"></td>