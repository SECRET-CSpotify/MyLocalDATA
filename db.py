# db.py
import streamlit as st   # <-- este faltaba
import os
from sqlalchemy import create_engine, text
import pandas as pd

DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_PORT = st.secrets["DB_PORT"]

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
                username TEXT,               -- <-- añadido
                tipo_operacion TEXT,
                modalidad TEXT,
                origen TEXT,
                destino TEXT,
                mercancia TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_clientes_username ON clientes(username);
        """))

def agregar_cliente(datos):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO clientes (
                nombre, nit, contacto, telefono, email, ciudad,
                fecha_contacto, observacion, contactado, username
            ) VALUES (
                :nombre, :nit, :contacto, :telefono, :email, :ciudad,
                :fecha_contacto, :observacion, :contactado, :username
            )
        """), datos)

def obtener_clientes(contactado=None, username=None, is_admin=False):
    sql = "SELECT * FROM clientes"
    clauses = []
    params = {}
    if contactado is not None:
        clauses.append("contactado = :contactado")
        params["contactado"] = contactado
    if username and not is_admin:
        clauses.append("username = :username")
        params["username"] = username
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return pd.read_sql(sql, engine, params=params)

def actualizar_cliente_detalle(cliente_id, datos):
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE clientes
            SET tipo_operacion=:tipo_operacion,
                modalidad=:modalidad,
                origen=:origen,
                destino=:destino,
                mercancia=:mercancia
            WHERE id=:id
        """), {"id": cliente_id, **datos})
