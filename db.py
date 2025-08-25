# db.py
import os
from sqlalchemy import create_engine, text
import pandas as pd

DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT")

# Crear motor de conexión
engine = create_engine(
    f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# --------------------------
# Funciones auxiliares
# --------------------------
def crear_tabla():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nombre TEXT,
                nit TEXT,
                contacto TEXT,
                telefono TEXT,
                email TEXT,
                ciudad TEXT,
                fecha_contacto DATE,
                observacion TEXT,
                contactado BOOLEAN DEFAULT FALSE,
                tipo_operacion TEXT,
                modalidad TEXT,
                origen TEXT,
                destino TEXT,
                mercancia TEXT
            );
        """))

def agregar_cliente(datos):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO clientes (nombre, nit, contacto, telefono, email, ciudad, fecha_contacto, observacion, contactado)
            VALUES (:nombre, :nit, :contacto, :telefono, :email, :ciudad, :fecha_contacto, :observacion, :contactado)
        """), datos)

def obtener_clientes(contactado=None):
    query = "SELECT * FROM clientes"
    if contactado is not None:
        query += f" WHERE contactado={str(contactado).lower()}"
    return pd.read_sql(query, engine)

def actualizar_cliente_detalle(cliente_id, datos):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE clientes
            SET tipo_operacion=:tipo_op,
                modalidad=:modalidad,
                origen=:origen,
                destino=:destino,
                mercancia=:mercancia
            WHERE id=:id
        """), {"id": cliente_id, **datos})
