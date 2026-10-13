import os
from pathlib import Path
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def conectar_bd():
    faltantes = [n for n in ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME") if not os.getenv(n)]
    if faltantes:
        raise RuntimeError("Configura las variables de .env: " + ", ".join(faltantes))
    config = dict(
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        cursorclass=DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
        autocommit=False,
        charset="utf8mb4",
    )
    # RDS puede requerir TLS; indica la ruta al certificado CA de AWS.
    if os.getenv("DB_SSL_CA"):
        config["ssl_ca"] = os.environ["DB_SSL_CA"]
        config["ssl_verify_cert"] = True
        config["ssl_verify_identity"] = True
    return pymysql.connect(**config)

def probar_conexion():
    try:
        with conectar_bd() as conexion:
            with conexion.cursor() as cursor:
                cursor.execute("SELECT DATABASE() AS base_datos")
                print("Conexión exitosa:", cursor.fetchone()["base_datos"])
    except Exception as exc:
        print("Error de conexión:", exc)
        raise

if __name__ == "__main__":
    probar_conexion()
