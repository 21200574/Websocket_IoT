# Práctica 2.5 — API IoT con FastAPI, Amazon RDS y WebSocket

Este proyecto reutiliza los endpoints de la práctica anterior (`GET/POST /status` y `WS /ws`) y agrega la API de `vehiculo_iot` basada en **las 6 tablas y los 21 Stored Procedures originales**. No crea ni altera tablas.

## 1. Preparar el proyecto (Windows / VS Code)
Abre esta carpeta en VS Code. En PowerShell, desde la raíz:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Si ya tienes un `.venv` funcional, puedes reutilizarlo en vez de crear otro. Si PowerShell bloquea la activación, usa `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` en esa sesión.

## 2. Configurar Amazon RDS
Copia `.env.example` como `.env` y reemplaza host, usuario y contraseña con los de TU instancia.
No compartas ni subas `.env`. El Security Group de RDS debe permitir TCP 3306 **solo desde tu IP**.
Si RDS exige TLS, configura `DB_SSL_CA` con el certificado CA de AWS RDS.

```powershell
python -m app.database
```
Si sale "Conexión exitosa: vehiculo_iot", la configuración es correcta.

## 3. Ejecutar FastAPI
```powershell
python -m app.main
```
Abre http://127.0.0.1:8000/docs para probar GET y POST con Swagger UI.
WebSocket: `ws://127.0.0.1:8000/ws` (usar Thunder Client u otro cliente compatible).

## 4. Servicios principales
- `GET /vehiculos`
- `GET /vehiculos/{id_vehiculo}`
- `GET /vehiculos/{id_vehiculo}/comandos`
- `GET /vehiculos/{id_vehiculo}/estado`
- `GET /vehiculos/{id_vehiculo}/historial`
- `GET /vehiculos/{id_vehiculo}/demos`
- `GET /demos/{id_demo}/movimientos`
- `POST /movimiento` con `{"id_vehiculo":1,"id_comando":1}` (usa el id real del comando, NO su código)
- `POST /demos/1/ejecutar` (responde 202 e inicia ejecución local)
- `GET /procedimientos` (lista las firmas de los 21 SP)
- `POST /procedimientos/{nombre}` con `{"parametros":{"p_nombre":"...","p_modelo":"...", ...}}`. Los parámetros deben coincidir EXACTAMENTE con los del SP. **Cuidado: crear/actualizar/eliminar sí cambia RDS.**
- `GET /status`, `POST /status`, `WS /ws` (compatibilidad con la práctica anterior).

## 5. Comportamiento DEMO
- Lee los movimientos de `sp_obtener_movimientos_demo`, respetando `orden`, `duracion_ms` y `pausa_ms`.
- Actualiza `sp_actualizar_estado` y notifica por WebSocket.
- **No llama a `sp_registrar_historial`** durante la DEMO.
- No controla todavía la excavadora física; únicamente simula/publica el comando en tiempo real.
- La API debe permanecer encendida durante la DEMO; al reiniciar el servidor se cancelan tareas en curso.
- Por simplicidad se ejecuta con **un solo proceso Uvicorn**. No uses `--workers` ni despliegues varias instancias para esta práctica.
- La API no implementa autenticación; mantenla en localhost. No expongas este servidor públicamente.

## 6. Pruebas sugeridas
1. `GET /vehiculos` debe mostrar los vehículos ya poblados en RDS.
2. `GET /vehiculos/1/comandos` y `GET /vehiculos/1/estado`.
3. Abre WebSocket `/ws` antes de `POST /movimiento` y observa la notificación.
4. `GET /vehiculos/1/historial` debe incluir el movimiento manual.
5. `GET /demos/1/movimientos`, luego `POST /demos/1/ejecutar`.
6. Verifica en WebSocket cada movimiento y confirma que la DEMO no añadió registros al historial.

## Nota
Se incluye el SQL de referencia, pero **NO lo ejecutes otra vez** en RDS: el dump contiene `DROP TABLE IF EXISTS` y podría borrar los datos existentes. El proyecto solo necesita la base ya poblada.

## Cambios de revisión

- WebSocket por vehículo: `ws://127.0.0.1:8000/ws/vehiculos/1` (estado inicial y eventos del vehículo 1). El antiguo `/ws` se conserva para el estado JSON de la práctica anterior.
- Cancelar DEMO: `POST /vehiculos/1/demos/cancelar`.
- Historial: `GET /vehiculos/1/historial` devuelve máximo diez registros.
- Las llamadas administrativas `POST /procedimientos/{nombre}` requieren encabezado `X-Admin-Token`, que debe coincidir con `ADMIN_TOKEN` en `.env`. No compartas este valor.
- Los procedimientos están enumerados en `GET /procedimientos`. Su presencia no sustituye las pruebas funcionales ni las validaciones de cada operación.
- La DEMO no registra historial; antes y después de ejecutarla, consulta el historial para comprobarlo.
- La ejecución del software no implica movimiento físico confirmado.

**Seguridad:** rota la contraseña de RDS si alguna vez se mostró en capturas y mantén `.env` fuera de GitHub. El token administrativo protege el endpoint genérico; el control manual y la cancelación requieren autenticación adicional antes de exponer esta API en una red pública.
