from fastapi import WebSocket

class WebSocketManager:
    def __init__(self):
        self.clientes: dict[WebSocket, int | None] = {}

    async def conectar(self, websocket: WebSocket, id_vehiculo: int | None = None):
        await websocket.accept()
        self.clientes[websocket] = id_vehiculo

    def desconectar(self, websocket: WebSocket):
        self.clientes.pop(websocket, None)

    async def enviar_a_vehiculo(self, id_vehiculo: int, mensaje):
        for cliente, vehiculo in list(self.clientes.items()):
            if vehiculo != id_vehiculo:
                continue
            try:
                await cliente.send_json(mensaje)
            except Exception:
                self.desconectar(cliente)

    async def enviar_a_todos(self, mensaje):
        for cliente in list(self.clientes):
            try:
                await cliente.send_json(mensaje)
            except Exception:
                self.desconectar(cliente)
