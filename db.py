import streamlit as st
import os
import pandas as pd
from sqlalchemy import create_engine, text
import urllib.parse

# --- Leer secrets de Streamlit (asegúrate que estén definidos) ---
DB_USER = st.secrets["DB_USER"]
DB_PASS = st.secrets["DB_PASS"]
DB_HOST = st.secrets["DB_HOST"]
DB_NAME = st.secrets["DB_NAME"]
DB_PORT = st.secrets.get("DB_PORT", 5432)

# --- Codificar password para evitar errores si contiene caracteres especiales ---
DB_PASS_ENC = urllib.parse.quote_plus(str(DB_PASS))

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS_ENC}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require"

# Crear el motor de conexión (pool nativo de SQLAlchemy)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# --------------------------
# Funciones auxiliares
# --------------------------
def crear_tabla():
    """
    Crea la tabla 'clientes' (si no existe) y añade un índice por username/base.
    Hemos añadido la columna base_name para distinguir TRANSLOGISTIC de las bases privadas.
    """
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
                username TEXT,
                base_name TEXT,
                tipo_operacion TEXT,
                modalidad TEXT,
                origen TEXT,
                destino TEXT,
                mercancia TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_clientes_username ON clientes(username);
            CREATE INDEX IF NOT EXISTS idx_clientes_base_name ON clientes(base_name);
        """))

def agregar_cliente(datos):
    """
    datos debe incluir: nombre, nit, contacto, telefono, email, ciudad,
    fecha_contacto (YYYY-MM-DD), observacion, contactado (bool), username, base_name
    """
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO clientes (
                nombre, nit, contacto, telefono, email, ciudad,
                fecha_contacto, observacion, contactado, username, base_name
            ) VALUES (
                :nombre, :nit, :contacto, :telefono, :email, :ciudad,
                :fecha_contacto::date, :observacion, :contactado, :username, :base_name
            )
        """), datos)

def obtener_clientes(contactado=None, username=None, is_admin=False, base_name=None):
    """
    Retorna un pandas.DataFrame con el resultado.
    - Si el usuario NO es admin y viene username, filtramos por username (su base privada).
    - Si base_name se especifica, filtramos por esa base (útil para Admin).
    """
    sql = "SELECT * FROM clientes"
    clauses = []
    params = {}

    if contactado is not None:
        clauses.append("contactado = :contactado")
        params["contactado"] = contactado

    # si viene un filtro por base_name explícito, aplicarlo (admin)
    if base_name:
        clauses.append("base_name = :base_name")
        params["base_name"] = base_name
    else:
        # si no es admin y hay username, filtrar por username
        if username and not is_admin:
            clauses.append("username = :username")
            params["username"] = username

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    try:
        df = pd.read_sql(text(sql), engine, params=params)
    except Exception as e:
        # En caso de error devuelve DataFrame vacío y muestra el error en logs
        st.error(f"Error al leer la base de datos: {e}")
        return pd.DataFrame()
    return df

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
