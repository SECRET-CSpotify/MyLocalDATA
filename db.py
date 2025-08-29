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
    with engine.begin() as conn:
        # crear tabla si no existe (incluye base_name en caso de nueva tabla)
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
        """))

        # asegurarse de que, si ya existía la tabla, tenga la columna base_name
        conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS base_name TEXT;"))

        # crear índices si no existen
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clientes_username ON clientes(username);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clientes_base_name ON clientes(base_name);"))

        # asignar TRANSLOGISTIC a registros previos que no tienen base_name
        conn.execute(text("UPDATE clientes SET base_name = 'TRANSLOGISTIC' WHERE base_name IS NULL;"))

def agregar_cliente(datos):
    """
    Inserta un cliente en la tabla 'clientes' pero con validaciones:
    - asegura que fecha_contacto sea None o 'YYYY-MM-DD' (sin ::date en SQL)
    - asegura base_name con valor por defecto 'TRANSLOGISTIC' si no viene
    - captura y muestra errores claros
    """
    import streamlit as st  # db.py ya lo importaba antes, asegurarse
    datos2 = dict(datos or {})

    # Defaults y saneamiento
    datos2.setdefault("contactado", False)
    datos2.setdefault("base_name", "TRANSLOGISTIC")
    # Fecha: aceptar date object, string o None
    fc = datos2.get("fecha_contacto")
    if fc in (None, "", "None"):
        datos2["fecha_contacto"] = None
    else:
        # si es date/datetime, convertir a ISO YYYY-MM-DD
        try:
            if hasattr(fc, "isoformat"):
                datos2["fecha_contacto"] = fc.isoformat()
            else:
                # forzar str (esperamos 'YYYY-MM-DD' normalmente)
                datos2["fecha_contacto"] = str(fc)
        except Exception:
            datos2["fecha_contacto"] = None

    # Asegurar que llaves esperadas existan (evita KeyError en parámetros)
    for k in ("nombre","nit","contacto","telefono","email","ciudad","observacion","username","base_name"):
        datos2.setdefault(k, None)

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO clientes (
                    nombre, nit, contacto, telefono, email, ciudad,
                    fecha_contacto, observacion, contactado, username, base_name
                ) VALUES (
                    :nombre, :nit, :contacto, :telefono, :email, :ciudad,
                    :fecha_contacto, :observacion, :contactado, :username, :base_name
                )
            """), datos2)
    except Exception as e:
        # Mostrar en logs y re-levantar para que la UI pueda capturarlo
        # Si quieres que no detenga la app, puedes quitar el 'raise'
        st.error(f"Error al insertar cliente en la base de datos: {e}")
        raise

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
