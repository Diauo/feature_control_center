from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.scheduled_task_service import get_active_scheduled_tasks
from app.services.feature_service import execute_feature
import atexit
from app.util.log_utils import logger

class TaskScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.job_mapping = {}  # 映射定时任务ID到APScheduler任务ID
        self.app = None  # Flask应用实例引用
        
    def init_app(self, app):
        """初始化应用实例"""
        self.app = app
        
    def start(self):
        """启动调度器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("定时任务调度器已启动")
            # 注册退出时停止调度器
            atexit.register(lambda: self.shutdown())
            
    def shutdown(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("定时任务调度器已停止")
            
    def load_scheduled_tasks(self):
        """从数据库加载所有启用的定时任务"""
        status, msg, tasks = get_active_scheduled_tasks()
        if not status:
            logger.error(f"加载定时任务失败: {msg}")
            return
            
        for task in tasks:
            self.add_job(task)
            
        logger.info(f"已加载 {len(tasks)} 个定时任务")
        
    def add_job(self, task):
        """添加定时任务到调度器"""
        # 确保在Flask应用上下文中执行
        if self.app:
            with self.app.app_context():
                self._add_job_internal(task)
        else:
            # 如果没有设置app实例，直接执行
            self._add_job_internal(task)
            
    def _add_job_internal(self, task):
        """内部方法：添加定时任务到调度器"""
        try:
            # 创建cron触发器
            trigger = CronTrigger.from_crontab(task['cron_expression'])
            
            # 添加任务到调度器
            job = self.scheduler.add_job(
                func=self.execute_scheduled_task,
                trigger=trigger,
                id=f"scheduled_task_{task['id']}",
                args=[task['id'], task['feature_id']],
                name=task['name']
            )
            
            # 记录映射关系
            self.job_mapping[task['id']] = job.id
            
            logger.info(f"已添加定时任务: {task['name']} (ID: {task['id']})")
        except Exception as e:
            logger.error(f"添加定时任务失败: {e}")
            
    def remove_job(self, task_id):
        """从调度器中移除定时任务"""
        # 确保在Flask应用上下文中执行
        if self.app:
            with self.app.app_context():
                self._remove_job_internal(task_id)
        else:
            # 如果没有设置app实例，直接执行
            self._remove_job_internal(task_id)
            
    def _remove_job_internal(self, task_id):
        """内部方法：从调度器中移除定时任务"""
        try:
            if task_id in self.job_mapping:
                job_id = self.job_mapping[task_id]
                self.scheduler.remove_job(job_id)
                del self.job_mapping[task_id]
                logger.info(f"已移除定时任务 ID: {task_id}")
        except Exception as e:
            logger.error(f"移除定时任务失败: {e}")
            
    def update_job(self, task):
        """更新调度器中的定时任务"""
        # 确保在Flask应用上下文中执行
        if self.app:
            with self.app.app_context():
                self._update_job_internal(task)
        else:
            # 如果没有设置app实例，直接执行
            self._update_job_internal(task)
            
    def _update_job_internal(self, task):
        """内部方法：更新调度器中的定时任务"""
        # 先移除旧任务
        self.remove_job(task['id'])
        # 如果任务是启用的，再添加新任务
        if task.get('is_active', False):
            self.add_job(task)
        
    def execute_scheduled_task(self, task_id, feature_id):
        """执行定时任务"""
        try:
            logger.info(f"开始执行定时任务 ID: {task_id}, 功能 ID: {feature_id}")
            # 使用特殊客户端ID标识定时任务执行
            client_id = f"scheduled_task_{task_id}"
            # 执行功能
            # 确保在Flask应用上下文中执行
            if self.app:
                with self.app.app_context():
                    status, msg, _ = execute_feature(feature_id, client_id, execution_type="scheduled")
            else:
                logger.error(f"执行定时任务失败，未设置Flask应用上下文: {task_id}")
                return
                    
            if status:
                logger.info(f"定时任务执行成功: {msg}")
            else:
                logger.error(f"定时任务执行失败: {msg}")
        except Exception as e:
            logger.error(f"执行定时任务时发生异常: {e}")

# 创建全局调度器实例
task_scheduler = TaskScheduler()