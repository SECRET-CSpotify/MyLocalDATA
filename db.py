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
        # Tabla principal clientes (agregada columna direccion)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                nombre TEXT,
                nit TEXT,
                contacto TEXT,
                telefono TEXT,
                email TEXT,
                ciudad TEXT,
                direccion TEXT,
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

        # Asegurar columnas existentes en caso de migración
        conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS direccion TEXT;"))
        conn.execute(text("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS base_name TEXT;"))

        # Índices para búsqueda rápida
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clientes_username ON clientes(username);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_clientes_base_name ON clientes(base_name);"))

        # Normalizar base_name faltante a TRANSLOGISTIC
        conn.execute(text("UPDATE clientes SET base_name = 'TRANSLOGISTIC' WHERE base_name IS NULL;"))

        # Tabla para persistir el nombre mostrado de la base privada por usuario
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                display_base_name TEXT
            );
        """))

        # Tabla para historial de contactos por cliente
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS contactos (
                id SERIAL PRIMARY KEY,
                cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
                fecha DATE,
                tipo TEXT,
                notas TEXT DEFAULT ''
            );
        """))

        # Tabla para agenda de visitas/recordatorios (sin notificaciones externas)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS visitas (
                id SERIAL PRIMARY KEY,
                cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
                fecha DATE,
                medio TEXT,
                creado_por TEXT,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

def agregar_cliente(datos):
    import streamlit as st
    datos2 = dict(datos or {})

    # Defaults y saneamiento
    datos2.setdefault("contactado", False)
    datos2.setdefault("base_name", "TRANSLOGISTIC")
    datos2.setdefault("direccion", None)

    # Si contactado == False, no se guarda fecha_contacto (lógico)
    fc = datos2.get("fecha_contacto")
    if not datos2.get("contactado"):
        datos2["fecha_contacto"] = None
    else:
        if fc in (None, "", "None"):
            datos2["fecha_contacto"] = None
        else:
            try:
                if hasattr(fc, "isoformat"):
                    datos2["fecha_contacto"] = fc.isoformat()
                else:
                    datos2["fecha_contacto"] = str(fc)
            except Exception:
                datos2["fecha_contacto"] = None

    # Asegurar llaves esperadas
    for k in ("nombre","nit","contacto","telefono","email","ciudad","observacion","username","base_name","direccion"):
        datos2.setdefault(k, None)

    # Normalizar base_name privada para evitar colisiones:
    # Si base_name no es TRANSLOGISTIC y parece ser un display name, lo guardamos como "{username}__{display}" internamente.
    if datos2["base_name"] and datos2["base_name"] != "TRANSLOGISTIC" and datos2.get("username"):
        # Si el usuario paso un display name (sin prefijo), lo convertimos
        if "__" not in datos2["base_name"]:
            datos2["base_name"] = f"{datos2['username']}__{datos2['base_name']}"

    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO clientes (
                    nombre, nit, contacto, telefono, email, ciudad, direccion,
                    fecha_contacto, observacion, contactado, username, base_name
                ) VALUES (
                    :nombre, :nit, :contacto, :telefono, :email, :ciudad, :direccion,
                    :fecha_contacto, :observacion, :contactado, :username, :base_name
                )
            """), datos2)
    except Exception as e:
        st.error(f"Error al insertar cliente en la base de datos: {e}")
        raise

def obtener_clientes(contactado=None, username=None, is_admin=False, base_name=None):
    sql = "SELECT * FROM clientes"
    clauses = []
    params = {}

    if contactado is not None:
        clauses.append("contactado = :contactado")
        params["contactado"] = contactado

    # Si se pasa base_name y es EXACTO "TRANSLOGISTIC" -> mostrar esa base para todos
    if base_name:
        # Si viene un display base (sin prefijo) para usuarios privados, no aplicamos aquí — espera que el caller pase el value correcto.
        clauses.append("base_name = :base_name")
        params["base_name"] = base_name
    else:
        # Si no es admin y hay username, usar su base privada interna (username__display) por defecto
        if username and not is_admin:
            # buscamos el display guardado; si no hay display, usar nombre por defecto "{username}_PRIVADA"
            try:
                display = get_display_base_name(username)
                if display:
                    internal = f"{username}__{display}"
                else:
                    internal = f"{username}__{username}_PRIVADA"
                clauses.append("base_name = :base_name")
                params["base_name"] = internal
            except Exception:
                clauses.append("username = :username")
                params["username"] = username

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    try:
        df = pd.read_sql(text(sql), engine, params=params)
    except Exception as e:
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

# --- Debe decir (agregar estas funciones nuevas) ---
def eliminar_cliente(cliente_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM clientes WHERE id = :id"), {"id": cliente_id})

def set_display_base_name(username, display_name):
    # guarda/actualiza en users
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO users (username, display_base_name)
            VALUES (:username, :display_base_name)
            ON CONFLICT (username) DO UPDATE SET display_base_name = EXCLUDED.display_base_name
        """), {"username": username, "display_base_name": display_name})

def get_display_base_name(username):
    with engine.begin() as conn:
        res = conn.execute(text("SELECT display_base_name FROM users WHERE username = :username"), {"username": username}).fetchone()
        return res[0] if res else None

def agendar_visita(cliente_id, fecha, medio, creado_por):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO visitas (cliente_id, fecha, medio, creado_por)
            VALUES (:cliente_id, :fecha, :medio, :creado_por)
        """), {"cliente_id": cliente_id, "fecha": fecha, "medio": medio, "creado_por": creado_por})

def obtener_visitas(cliente_id):
    with engine.begin() as conn:
        df = pd.read_sql(text("SELECT * FROM visitas WHERE cliente_id = :cliente_id ORDER BY fecha DESC"), engine, params={"cliente_id": cliente_id})
        return df

def agregar_contacto(cliente_id, fecha, tipo, notas=""):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO contactos (cliente_id, fecha, tipo, notas)
            VALUES (:cliente_id, :fecha, :tipo, :notas)
        """), {"cliente_id": cliente_id, "fecha": fecha, "tipo": tipo, "notas": notas})

def obtener_contactos(cliente_id):
    df = pd.DataFrame()
    try:
        df = pd.read_sql(text("SELECT * FROM contactos WHERE cliente_id = :cliente_id ORDER BY fecha DESC"), engine, params={"cliente_id": cliente_id})
    except Exception:
        pass
    return df

