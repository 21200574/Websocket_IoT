import asyncio
import os
import secrets
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Header, Depends
from fastapi.encoders import jsonable_encoder
from pymysql import MySQLError

from app.models.estado import Estado
from app.models.vehiculo import Movimiento, EjecutarProcedimiento
from app.services.status_service import StatusService
from app.services.vehiculo_service import PROCEDIMIENTOS, ejecutar, consultar, movimiento_manual
from app.websocket.websocket_manager import WebSocketManager

status_service = StatusService()
websocket_manager = WebSocketManager()
demo_tareas = {}
demo_bloqueos = {}

def marca_tiempo():
    return datetime.now(timezone.utc).isoformat()

def autorizar_admin(x_admin_token: str | None = Header(default=None)):
    token = os.getenv("ADMIN_TOKEN")
    if not token:
        raise HTTPException(503, "Configura ADMIN_TOKEN en .env para habilitar operaciones administrativas")
    if not x_admin_token or not secrets.compare_digest(x_admin_token, token):
        raise HTTPException(403, "Token administrativo inválido")

@asynccontextmanager
async def lifespan(app):
    yield
    for tarea in demo_tareas.values():
        if not tarea.done():
            tarea.cancel()
    if demo_tareas:
        await asyncio.gather(*demo_tareas.values(), return_exceptions=True)

app = FastAPI(title="Vehículo IoT - Práctica 2.5",
              description="FastAPI, 21 Stored Procedures de Amazon RDS y WebSocket. Ejecución local.",
              version="2.5", lifespan=lifespan)

def error_bd(exc):
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc))
    raise HTTPException(status_code=503, detail="No se pudo completar la operación en Amazon RDS. Revisa el servidor.")

@app.get("/")
def inicio():
    return {"proyecto": "Práctica 2.5", "docs": "/docs", "websocket": "/ws"}

# Endpoints conservados de la práctica anterior.
@app.get("/status", tags=["Práctica anterior"])
def obtener_estado():
    return status_service.obtener_estado()

@app.post("/status", tags=["Práctica anterior"])
async def cambiar_estado(estado: Estado):
    nuevo_estado = status_service.guardar_estado(estado.status)
    await websocket_manager.enviar_a_todos(nuevo_estado)
    return nuevo_estado

@app.websocket("/ws/vehiculos/{id_vehiculo}")
async def websocket_vehiculo(websocket: WebSocket, id_vehiculo: int):
    if id_vehiculo <= 0:
        await websocket.close(code=1008)
        return
    try:
        estado = await asyncio.to_thread(consultar, "sp_obtener_estado", p_id_vehiculo=id_vehiculo)
    except Exception:
        await websocket.close(code=1011)
        return
    await websocket_manager.conectar(websocket, id_vehiculo)
    await websocket.send_json({"tipo": "estado_inicial", "id_vehiculo": id_vehiculo,
                               "estado": estado, "fecha_hora": marca_tiempo()})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.desconectar(websocket)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_manager.conectar(websocket)
    await websocket.send_json(status_service.obtener_estado())
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        websocket_manager.desconectar(websocket)

@app.get("/vehiculos", tags=["Consultas RDS"])
def vehiculos():
    try:
        return consultar("sp_obtener_vehiculos")
    except Exception as exc:
        error_bd(exc)

@app.get("/vehiculos/{id_vehiculo}", tags=["Consultas RDS"])
def vehiculo(id_vehiculo: int):
    try:
        return consultar("sp_obtener_vehiculo", p_id_vehiculo=id_vehiculo)
    except Exception as exc:
        error_bd(exc)

@app.get("/vehiculos/{id_vehiculo}/comandos", tags=["Consultas RDS"])
def comandos(id_vehiculo: int):
    try:
        return consultar("sp_obtener_comandos_vehiculo", p_id_vehiculo=id_vehiculo)
    except Exception as exc:
        error_bd(exc)

@app.get("/vehiculos/{id_vehiculo}/estado", tags=["Consultas RDS"])
def estado_vehiculo(id_vehiculo: int):
    try:
        return consultar("sp_obtener_estado", p_id_vehiculo=id_vehiculo)
    except Exception as exc:
        error_bd(exc)

@app.get("/vehiculos/{id_vehiculo}/historial", tags=["Consultas RDS"])
def historial(id_vehiculo: int):
    try:
        return consultar("sp_obtener_historial", p_id_vehiculo=id_vehiculo)[:10]
    except Exception as exc:
        error_bd(exc)

@app.get("/vehiculos/{id_vehiculo}/demos", tags=["Consultas RDS"])
def demos(id_vehiculo: int):
    try:
        return consultar("sp_obtener_demos", p_id_vehiculo=id_vehiculo)
    except Exception as exc:
        error_bd(exc)

@app.get("/demos/{id_demo}/movimientos", tags=["Consultas RDS"])
def movimientos_demo(id_demo: int):
    try:
        return consultar("sp_obtener_movimientos_demo", p_id_demo=id_demo)
    except Exception as exc:
        error_bd(exc)

@app.post("/movimiento", tags=["Movimientos"])
async def enviar_movimiento(mov: Movimiento):
    if mov.id_vehiculo in demo_tareas and not demo_tareas[mov.id_vehiculo].done():
        raise HTTPException(409, "Hay una DEMO en ejecución para este vehículo")
    try:
        resultado = await asyncio.to_thread(movimiento_manual, mov.id_vehiculo, mov.id_comando)
        await websocket_manager.enviar_a_vehiculo(mov.id_vehiculo, {
            "tipo": "movimiento_manual", "id_vehiculo": mov.id_vehiculo,
            "id_comando": mov.id_comando, "estado": resultado, "fecha_hora": marca_tiempo()
        })
        return {"mensaje": "Movimiento registrado", "estado": resultado}
    except Exception as exc:
        error_bd(exc)

async def ejecutar_demo(id_vehiculo, id_demo, movimientos):
    try:
        await websocket_manager.enviar_a_vehiculo(id_vehiculo, {
            "tipo": "demo_inicio", "id_vehiculo": id_vehiculo, "id_demo": id_demo, "fecha_hora": marca_tiempo()
        })
        for mov in movimientos:
            id_comando = mov["id_comando"]
            # DEMO: actualiza estado sin registrar en historial.
            await asyncio.to_thread(ejecutar, "sp_actualizar_estado", {
                "p_id_vehiculo": id_vehiculo, "p_id_comando": id_comando, "p_conectado": True
            })
            await websocket_manager.enviar_a_vehiculo(id_vehiculo, {
                "tipo": "demo_movimiento", "id_vehiculo": id_vehiculo, "id_demo": id_demo,
                "orden": mov["orden"], "id_comando": id_comando,
                "comando": mov["comando"], "codigo": mov["codigo"],
                "duracion_ms": mov["duracion_ms"], "pausa_ms": mov["pausa_ms"], "fecha_hora": marca_tiempo()
            })
            await asyncio.sleep(mov["duracion_ms"] / 1000)
            await asyncio.sleep(mov["pausa_ms"] / 1000)
        await websocket_manager.enviar_a_vehiculo(id_vehiculo, {
            "tipo": "demo_fin", "id_vehiculo": id_vehiculo, "id_demo": id_demo, "fecha_hora": marca_tiempo()
        })
    except asyncio.CancelledError:
        await websocket_manager.enviar_a_vehiculo(id_vehiculo, {
            "tipo": "demo_cancelada", "id_vehiculo": id_vehiculo, "id_demo": id_demo, "fecha_hora": marca_tiempo()
        })
        raise
    except Exception:
        await websocket_manager.enviar_a_vehiculo(id_vehiculo, {
            "tipo": "demo_error", "id_vehiculo": id_vehiculo, "id_demo": id_demo, "fecha_hora": marca_tiempo()
        })

@app.post("/vehiculos/{id_vehiculo}/demos/cancelar", tags=["Movimientos"])
async def cancelar_demo(id_vehiculo: int):
    tarea = demo_tareas.get(id_vehiculo)
    if tarea is None or tarea.done():
        raise HTTPException(404, "No hay DEMO activa para este vehículo")
    tarea.cancel()
    try:
        await tarea
    except asyncio.CancelledError:
        pass
    return {"mensaje": "DEMO cancelada", "id_vehiculo": id_vehiculo}

@app.post("/demos/{id_demo}/ejecutar", tags=["Movimientos"], status_code=202)
async def iniciar_demo(id_demo: int):
    try:
        # Identifica el vehículo dueño de la DEMO.
        vehiculos = await asyncio.to_thread(consultar, "sp_obtener_vehiculos")
        dueño = None
        for veh in vehiculos:
            lista = await asyncio.to_thread(consultar, "sp_obtener_demos", p_id_vehiculo=veh["id_vehiculo"])
            if veh.get("activo") and any(d["id_demo"] == id_demo and d["activo"] for d in lista):
                dueño = veh["id_vehiculo"]
                break
        if dueño is None:
            raise HTTPException(404, "DEMO activa no encontrada")
        movimientos = await asyncio.to_thread(consultar, "sp_obtener_movimientos_demo", p_id_demo=id_demo)
        if not movimientos:
            raise HTTPException(400, "La DEMO no tiene movimientos")
        comandos = await asyncio.to_thread(consultar, "sp_obtener_comandos_vehiculo", p_id_vehiculo=dueño)
        validos = {c["id_comando"] for c in comandos if c["activo"]}
        if any(m["id_comando"] not in validos for m in movimientos):
            raise HTTPException(400, "La DEMO contiene comandos inactivos o de otro vehículo")
        if dueño in demo_tareas and not demo_tareas[dueño].done():
            raise HTTPException(409, "Ya hay una DEMO ejecutándose para este vehículo")
        bloqueo = demo_bloqueos.setdefault(dueño, asyncio.Lock())
        async with bloqueo:
            if dueño in demo_tareas and not demo_tareas[dueño].done():
                raise HTTPException(409, "Ya hay una DEMO ejecutándose para este vehículo")
            tarea = asyncio.create_task(ejecutar_demo(dueño, id_demo, movimientos))
            demo_tareas[dueño] = tarea
        return {"mensaje": "DEMO iniciada", "id_demo": id_demo,
                "id_vehiculo": dueño, "movimientos": len(movimientos)}
    except HTTPException:
        raise
    except Exception as exc:
        error_bd(exc)

@app.get("/procedimientos", tags=["21 Stored Procedures"])
def listar_procedimientos():
    return PROCEDIMIENTOS

@app.post("/procedimientos/{nombre}", tags=["21 Stored Procedures"])
async def llamar_procedimiento(nombre: str, cuerpo: EjecutarProcedimiento, _: None = Depends(autorizar_admin)):
    if nombre not in PROCEDIMIENTOS:
        raise HTTPException(404, "Procedimiento no reconocido")
    # Evita alterar estados/historial durante una DEMO desde el endpoint genérico.
    if nombre in {"sp_actualizar_estado", "sp_registrar_historial"}:
        raise HTTPException(409, "Usa /movimiento para movimientos manuales o /demos/{id_demo}/ejecutar para DEMO")
    try:
        if nombre.startswith("sp_obtener_"):
            resultado = await asyncio.to_thread(ejecutar, nombre, cuerpo.parametros)
        else:
            resultado = await asyncio.to_thread(ejecutar, nombre, cuerpo.parametros)
        return {"procedimiento": nombre, "resultado": jsonable_encoder(resultado)}
    except Exception as exc:
        error_bd(exc)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
