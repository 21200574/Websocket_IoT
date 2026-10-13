from datetime import date, datetime
from decimal import Decimal
from app.database import conectar_bd

# Firmas exactas del archivo vehiculo_iot_rds(2).sql (21 procedimientos).
PROCEDIMIENTOS = {
    "sp_actualizar_comando": ["p_id_comando","p_nombre","p_codigo","p_descripcion","p_activo"],
    "sp_actualizar_demo": ["p_id_demo","p_nombre","p_descripcion","p_activo"],
    "sp_actualizar_estado": ["p_id_vehiculo","p_id_comando","p_conectado"],
    "sp_actualizar_movimiento_demo": ["p_id_demo_movimiento","p_id_comando","p_orden","p_duracion_ms","p_pausa_ms"],
    "sp_actualizar_vehiculo": ["p_id_vehiculo","p_nombre","p_modelo","p_descripcion","p_microcontrolador","p_activo"],
    "sp_agregar_movimiento_demo": ["p_id_demo","p_id_comando","p_orden","p_duracion_ms","p_pausa_ms"],
    "sp_crear_comando": ["p_id_vehiculo","p_nombre","p_codigo","p_descripcion"],
    "sp_crear_demo": ["p_id_vehiculo","p_nombre","p_descripcion"],
    "sp_crear_vehiculo": ["p_nombre","p_modelo","p_descripcion","p_microcontrolador"],
    "sp_eliminar_comando": ["p_id_comando"],
    "sp_eliminar_demo": ["p_id_demo"],
    "sp_eliminar_movimiento_demo": ["p_id_demo_movimiento"],
    "sp_eliminar_vehiculo": ["p_id_vehiculo"],
    "sp_obtener_comandos_vehiculo": ["p_id_vehiculo"],
    "sp_obtener_demos": ["p_id_vehiculo"],
    "sp_obtener_estado": ["p_id_vehiculo"],
    "sp_obtener_historial": ["p_id_vehiculo"],
    "sp_obtener_movimientos_demo": ["p_id_demo"],
    "sp_obtener_vehiculo": ["p_id_vehiculo"],
    "sp_obtener_vehiculos": [],
    "sp_registrar_historial": ["p_id_vehiculo","p_id_comando","p_origen"],
}

def serializar(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: serializar(v) for k,v in obj.items()}
    if isinstance(obj, list):
        return [serializar(v) for v in obj]
    return obj

def ejecutar(nombre: str, parametros=None, conexion=None):
    if nombre not in PROCEDIMIENTOS:
        raise ValueError("Procedimiento no permitido")
    parametros = parametros or {}
    firma = PROCEDIMIENTOS[nombre]
    if set(parametros) != set(firma):
        raise ValueError(f"{nombre} requiere exactamente: {', '.join(firma) or '(sin parámetros)'}")
    propia = conexion is None
    if propia:
        conexion = conectar_bd()
    try:
        with conexion.cursor() as cursor:
            marcadores = ", ".join(["%s"] * len(firma))
            cursor.execute(f"CALL {nombre}({marcadores})", tuple(parametros[p] for p in firma))
            conjuntos = []
            while True:
                if cursor.description:
                    filas = cursor.fetchall()
                    # PyMySQL puede generar un resultado vacío adicional de CALL.
                    conjuntos.append(serializar(list(filas)))
                if not cursor.nextset():
                    break
        if propia:
            conexion.commit()
        return conjuntos[0] if len(conjuntos) == 1 else (conjuntos[0] if conjuntos else [])
    except Exception:
        if propia:
            conexion.rollback()
        raise
    finally:
        if propia:
            conexion.close()

def consultar(nombre, **kwargs):
    return ejecutar(nombre, kwargs)

def movimiento_manual(id_vehiculo, id_comando):
    # Validación de pertenencia y actividad antes de escribir.
    with conectar_bd() as conexion:
        try:
            vehiculos = ejecutar("sp_obtener_vehiculo", {"p_id_vehiculo": id_vehiculo}, conexion)
            if not vehiculos or not vehiculos[0].get("activo"):
                raise ValueError("Vehículo inexistente o inactivo")
            comandos = ejecutar("sp_obtener_comandos_vehiculo", {"p_id_vehiculo": id_vehiculo}, conexion)
            if not any(c["id_comando"] == id_comando and c["activo"] for c in comandos):
                raise ValueError("Comando inexistente, inactivo o no pertenece al vehículo")
            ejecutar("sp_actualizar_estado", {
                "p_id_vehiculo": id_vehiculo, "p_id_comando": id_comando, "p_conectado": True
            }, conexion)
            ejecutar("sp_registrar_historial", {
                "p_id_vehiculo": id_vehiculo, "p_id_comando": id_comando, "p_origen": "MANUAL"
            }, conexion)
            conexion.commit()
        except Exception:
            conexion.rollback()
            raise
    return consultar("sp_obtener_estado", p_id_vehiculo=id_vehiculo)
