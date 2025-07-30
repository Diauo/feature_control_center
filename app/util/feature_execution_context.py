from flask_socketio import emit
from app.ws_server import socketio, client_sid_map
import logging
import os

LOG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../logs"))
os.makedirs(LOG_DIR, exist_ok=True)

class FeatureExecutionContext:
    def __init__(self, client_id, feature_name=None, namespace="/feature"):
        self.client_id = client_id
        self.namespace = namespace
        self.feature_name = feature_name or "未知功能"

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

    def log(self, message, level="info", send_ws=True):
        # 只写文件日志
        for handler in self.logger.handlers:
            if isinstance(handler, WebSocketLogHandler):
                handler.set_send_ws(send_ws)
        if hasattr(self.logger, level):
            getattr(self.logger, level)(message)
        else:
            self.logger.info(message)
        # 恢复handler为默认（下次log不影响）
        for handler in self.logger.handlers:
            if isinstance(handler, WebSocketLogHandler):
                handler.set_send_ws(True)

    def done(self, msg="功能已完成", data=None):
        emit('feature_done', {
            'client_id': self.client_id,
            'status': 'success',
            'msg': msg,
            'data': data or {}
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)

    def error(self, msg="功能执行失败", data=None):
        emit('feature_done', {
            'client_id': self.client_id,
            'status': 'error',
            'msg': msg,
            'data': data or {}
        }, room=client_sid_map.get(self.client_id), namespace=self.namespace)

    def terminate(self, reason="任务被终止"):
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