"""
WebSocket 连接管理器
负责维护所有前端实时连接，有新数据时广播推送
"""
from fastapi import WebSocket
from typing import List
import json


class ConnectionManager:
    def __init__(self):
        # 保存所有活跃的 WebSocket 连接
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """向所有连接广播 JSON 消息"""
        text = json.dumps(message, ensure_ascii=False, default=str)
        # 复制列表防止遍历时修改
        for conn in self.active_connections.copy():
            try:
                await conn.send_text(text)
            except Exception:
                # 发送失败则移除断开的连接
                self.disconnect(conn)


# 全局单例，整个应用共享一个管理器
manager = ConnectionManager()
