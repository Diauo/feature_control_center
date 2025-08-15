import  api  from './api.js';

export const scheduled_task_api = {
  // 获取所有定时任务
  getAllScheduledTasks() {
    return api.client.get('/scheduled-task/get_all');
  },

  // 根据ID获取定时任务
  getScheduledTaskById(taskId) {
    return api.client.get(`/scheduled-task/get/${taskId}`);
  },

  // 添加新定时任务
  addScheduledTask(taskData) {
    return api.client.post('/scheduled-task/add', taskData);
  },

  // 更新指定ID的定时任务
  updateScheduledTask(taskId, taskData) {
    return api.client.put(`/scheduled-task/update/${taskId}`, taskData);
  },

  // 删除指定ID的定时任务
  deleteScheduledTask(taskId) {
    return api.client.delete(`/scheduled-task/delete/${taskId}`);
  },

  // 启用指定ID的定时任务
  enableScheduledTask(taskId) {
    return api.client.post(`/scheduled-task/enable/${taskId}`);
  },

  // 禁用指定ID的定时任务
  disableScheduledTask(taskId) {
    return api.client.post(`/scheduled-task/disable/${taskId}`);
  }
};

export default scheduled_task_api