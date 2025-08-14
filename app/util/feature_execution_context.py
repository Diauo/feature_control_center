from flask_socketio import emit
from app.ws_server import socketio, client_sid_map
import logging
from datetime import datetime
from app import db
from app.models.base_models import FeatureExecutionLog
from app.models.base_models import FeatureExecutionLog, FeatureExecutionLogDetail
import os
import time
LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
os.makedirs(LOG_DIR, exist_ok=True)

class FeatureExecutionContext:
    def __init__(self, client_id, feature_name=None, feature_id=None, namespace="/feature"):
        self.client_id = client_id
        self.namespace = namespace
        self.feature_name = feature_name or "未知功能"
        self.feature_id = feature_id
        # 生成唯一的requestId
        days_since_epoch = int(time.time()) // 86400 
        max_id = db.session.query(db.func.max(FeatureExecutionLog.id)).scalar() or 0
        next_id = max_id + 1
        self.request_id = f"{days_since_epoch:05d}{next_id}"

        # 初始化数据库日志记录
        self.db_log = FeatureExecutionLog(
            feature_id=self.feature_id,
            request_id=self.request_id,
            start_time=datetime.now(),
            status="运行中",
            client_id=self.client_id
        )
        db.session.add(self.db_log)
        db.session.commit()

        # ws handler: 只发纯消息
        self.logger = logging.getLogger(f"feature-{client_id}")
        self.logger.setLevel(logging.INFO)
        if not any(isinstance(h, WebSocketLogHandler) and getattr(h, "client_id", None) == client_id for h in self.logger.handlers):
            ws_handler = WebSocketLogHandler(client_id, namespace)
            self.logger.addHandler(ws_handler)

        # file handler: 带时间，按feature_name分文件
        log_file = os.path.join(LOG_DIR, f"{self.feature_name}.log")
        if not any(isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == os.path.abspath(log_file) for h in self.logger.handlers):
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
            self.logger.addHandler(file_handler)

        
        self.log(f"初始化完成，本次请求ID：{self.request_id}", "info")

    def log(self, message, level="info", send_ws=True):
        # 只写文件日志
        for handler in self.logger.handlers:
            if isinstance(handler, WebSocketLogHandler):
                handler.set_send_ws(send_ws)
        if hasattr(self.logger, level):
            getattr(self.logger, level)(message)
        else:
            self.logger.info(message)
        
        # 同时写入数据库明细表
        log_detail = FeatureExecutionLogDetail(
            log_id=self.db_log.id,
            level=level.upper(),
            message=message,
            request_id=self.request_id
        )
        db.session.add(log_detail)
        db.session.commit()
        
        # 恢复handler为默认（下次log不影响）
        for handler in self.logger.handlers:
            if isinstance(handler, WebSocketLogHandler):
                handler.set_send_ws(True)

    def done(self, msg="功能执行已完成", data=None):
        # 更新数据库日志记录
        self.db_log.end_time = datetime.now()
        self.db_log.status = "成功"
        db.session.commit()
        
        emit('feature_done', {
            'client_id': self.client_id,
            'status': 'success',
            'msg': msg,
            'data': data or {}
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)

    def fail(self, msg="功能执行失败", data=None):
        # 更新数据库日志记录
        self.db_log.end_time = datetime.now()
        self.db_log.status = "失败"
        db.session.commit()
        
        emit('feature_done', {
            'client_id': self.client_id,
            'status': 'error',
            'msg': msg,
            'data': data or {}
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)

    def error(self, msg="功能执行失败", data=None, exception=None):
        # 记录错误日志
        if exception:
            import traceback
            self.log(f"错误信息: {msg}", "error")
            self.log(f"异常信息: {str(exception)}", "error")
            self.log(f"异常堆栈: {traceback.format_exc()}", "error")
        else:
            self.log(f"错误信息: {msg}", "error")
            
        emit('feature_error', {
            'client_id': self.client_id,
            'status': 'error',
            'msg': msg,
            'data': data or {}
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)

    def terminate(self, reason="任务被终止"):
        # 更新数据库日志记录
        self.db_log.end_time = datetime.now()
        self.db_log.status = "终止"
        db.session.commit()
        
        emit('feature_done', {
            'client_id': self.client_id,
            'status': 'terminated',
            'msg': reason
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)


class WebSocketLogHandler(logging.Handler):
    def __init__(self, client_id=None, namespace="/feature"):
        super().__init__()
        self.namespace = namespace
        self.client_id = client_id
        self._send_ws = True

    def set_send_ws(self, send_ws):
        self._send_ws = send_ws

    def emit(self, record):
        if not self._send_ws:
            return
        sid = client_sid_map.get(self.client_id)
        if sid:
            socketio.emit('log', {'message': record.getMessage()}, room=sid, namespace=self.namespace)