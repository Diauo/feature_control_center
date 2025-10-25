from flask_socketio import SocketIO, emit, Namespace
from flask import request

socketio = SocketIO(cors_allowed_origins="*")  # 支持跨域

client_sid_map = {}  # client_id -> sid
sid_client_map = {}  # sid -> client_id

class FeatureNamespace(Namespace):
    def on_connect(self, sid, environ):
        print("WebSocket 已连接")
    def on_disconnect(self, sid):
        print("WebSocket 已断开")
    def on_register(self, sid, data):
        client_id = data.get("client_id")
        sid = request.sid
        if client_id:
            client_sid_map[client_id] = sid
            sid_client_map[sid] = client_id
            print(f"客户端注册: {client_id} <-> {sid}")

socketio.on_namespace(FeatureNamespace('/feature'))