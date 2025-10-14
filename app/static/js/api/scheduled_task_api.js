import  api  from './api.js';

export const scheduled_task_api = {
  // 获取所有定时任务（管理员）
  get_scheduled_tasks() {
    return api.client.post('/scheduled-task/get_scheduled_tasks');
  },

  // 获取定时任务（操作员）
  get_scheduled_tasks_by_customer_id(customer_id) {
    return api.client.post('/scheduled-task/get_scheduled_tasks_by_customer_id', { customer_id: customer_id });
  },

  // 根据ID获取定时任务
  get_scheduled_task(taskId) {
    return api.client.post('/scheduled-task/get_scheduled_task', { id: taskId });
  },

  // 添加新定时任务（管理员）
  add_scheduled_task(taskData) {
    return api.client.post('/scheduled-task/add_scheduled_task', taskData);
  },

  // 更新指定ID的定时任务（管理员）
  update_scheduled_task(taskId, taskData) {
    // 添加ID到数据中
    const data = { ...taskData, id: taskId };
    return api.client.post('/scheduled-task/update_scheduled_task', data);
  },

  // 删除指定ID的定时任务（管理员）
  del_scheduled_task(taskId) {
    return api.client.post('/scheduled-task/del_scheduled_task', { id: taskId });
  },

  // 启用指定ID的定时任务（管理员）
  enable_scheduled_task(taskId) {
    return api.client.post('/scheduled-task/enable_scheduled_task', { id: taskId });
  },

  // 禁用指定ID的定时任务（管理员）
  disable_scheduled_task(taskId) {
    return api.client.post('/scheduled-task/disable_scheduled_task', { id: taskId });
  }
};

export default scheduled_task_api;