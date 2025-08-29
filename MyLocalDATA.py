import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from db import crear_tabla, agregar_cliente, obtener_clientes, actualizar_cliente_detalle

# --------------------------
# Configuración general
# --------------------------
st.set_page_config(page_title="Gestor de Clientes", layout="wide")

# --------------------------
# ------------------ Bloque de autenticación robusto (pegar aquí) ------------------
import traceback

# Bloque de autenticación (sin debug)
# --------------------------
from collections.abc import Mapping

def normalize_credentials_from_secrets():
    """
    Devuelve un objeto {'usernames': {...}} listo para pasar a stauth.Authenticate.
    """
    creds = st.secrets.get("credentials")
    if creds and isinstance(creds, Mapping):
        if "usernames" in creds and isinstance(creds["usernames"], Mapping):
            return {"usernames": dict(creds["usernames"])}
        usernames = {}
        for k, v in dict(creds).items():
            if isinstance(v, Mapping) and ("name" in v or "email" in v or "password" in v):
                usernames[k] = {
                    "name": v.get("name"),
                    "email": v.get("email"),
                    "password": v.get("password")
                }
        if usernames:
            return {"usernames": usernames}
    users_list = st.secrets.get("USERS")
    if users_list and isinstance(users_list, list):
        usernames = {}
        for u in users_list:
            if not isinstance(u, dict):
                continue
            uname = u.get("username") or u.get("name")
            if not uname:
                continue
            usernames[uname] = {
                "name": u.get("name"),
                "email": u.get("email"),
                "password": u.get("password"),
            }
        if usernames:
            return {"usernames": usernames}
    return None

# Normalizar y validar credentials desde secrets
def normalize_credentials_from_secrets():
    """
    Devuelve un objeto {'usernames': {...}} listo para pasar a stauth.Authenticate.
    (He dejado tu función original por seguridad; la usamos aquí)
    """
    creds = st.secrets.get("credentials")
    if creds and isinstance(creds, dict):
        if "usernames" in creds and isinstance(creds["usernames"], dict):
            return {"usernames": dict(creds["usernames"])}
        usernames = {}
        for k, v in dict(creds).items():
            if isinstance(v, dict) and ("name" in v or "email" in v or "password" in v):
                usernames[k] = {
                    "name": v.get("name"),
                    "email": v.get("email"),
                    "password": v.get("password"),
                    # opcional: rol
                    "is_admin": v.get("is_admin", False)
                }
        if usernames:
            return {"usernames": usernames}
    # fallback a formato antiguo
    try:
        return {"usernames": st.secrets["credentials"]["usernames"]}
    except Exception:
        return None

credentials = normalize_credentials_from_secrets()
if credentials is None:
    st.error("Formato inválido en st.secrets['credentials']. Debe ser {'usernames':{...}}")
    st.stop()

# Validar cookies
missing = [k for k in ("COOKIE_NAME", "COOKIE_KEY", "COOKIE_EXPIRY_DAYS") if k not in st.secrets]
if missing:
    st.error("Faltan keys en secrets: " + ", ".join(missing))
    st.stop()

cookie_name = st.secrets["COOKIE_NAME"]
cookie_key = st.secrets["COOKIE_KEY"]
try:
    cookie_expiry = int(st.secrets["COOKIE_EXPIRY_DAYS"])
except Exception:
    st.error("COOKIE_EXPIRY_DAYS debe ser un número entero.")
    st.stop()

try:
    authenticator = stauth.Authenticate(
        credentials,     # ahora es un dict 100% mutable
        cookie_name,
        cookie_key,
        cookie_expiry
    )
except Exception as e:
    st.error(f"Error creando stauth.Authenticate: {e}")
    st.stop()


# Manejo correcto del retorno del login

authenticator.login(location="sidebar")

if st.session_state.get("authentication_status") is True:
    name = st.session_state["name"]
    username = st.session_state["username"]
    is_admin = (username == "admin")

    st.sidebar.success(f"Bienvenido, {name} 👋")
    authenticator.logout("Cerrar sesión", "sidebar", key="logout_button")

# --- Configuración de Base (TRANSLOGISTIC + Base Privada del usuario) ---
with st.sidebar.expander("Mi Base y Preferencias"):
    # nombre personalizado de la base privada (no persistente; para persistir recomiendo crear tabla 'users')
    default_private_name = f"{name}_PRIVADA"
    private_base_name = st.text_input("Nombre de tu base privada", value=st.session_state.get("private_base_name", default_private_name))
    # guardar en session_state para recordar durante la sesión
    st.session_state["private_base_name"] = private_base_name

    # Selección de dónde ver/guardar los registros
    selected_base_view = st.radio("¿Qué base quieres ver/usar por defecto?", ["TRANSLOGISTIC", private_base_name])
    st.session_state["selected_base_view"] = selected_base_view

# Si eres admin, permitir filtrado por username o por base
if is_admin:
    st.sidebar.markdown("**Panel Admin — filtros**")
    # lista de bases disponibles (consulta mínima)
    todas = obtener_clientes()  # ojo: esto devuelve todo; para apps grandes mejor consulta específica
    bases_disponibles = sorted(todas['base_name'].dropna().unique().tolist()) if not todas.empty else []
    bases_disponibles = ["TRANSLOGISTIC"] + [b for b in bases_disponibles if b != "TRANSLOGISTIC"]
    filtrar_base = st.sidebar.selectbox("Filtrar por base (Admin)", options=["Todas"] + bases_disponibles, index=0)
    filtrar_username = st.sidebar.text_input("Filtrar por username (dejar en blanco = todos)")
else:
    filtrar_base = None
    filtrar_username = None

    # --------------------------
    # Estilos personalizados
    # --------------------------
    page_bg = """
<style>
/* --- Fuente: opción A: usar Google Font disponible (recomendada) --- */
@import url('https://fonts.googleapis.com/css2?family=Faculty+Glyphic&display=swap');

:root {
    --main-font: 'Faculty Glyphic', sans-serif;
}

/* Aplicar fuente a todo */
html, body, [class*="css"], .stMarkdown, .stText, .stDataFrame, table {
    font-family: var(--main-font) !important;
}

/* Fondo animado */
[data-testid="stAppViewContainer"] {
    background: linear-gradient(-45deg, #23a6d5, #23d5ab, #ff6f61, #6a11cb);
    background-size: 400% 400%;
    animation: gradientBG 15s ease infinite;
    padding: 1rem;
}
@keyframes gradientBG {
    0% {background-position: 0% 50%;}
    50% {background-position: 100% 50%;}
    100% {background-position: 0% 50%;}
}

/* Títulos mejorados */
h1, h2, h3, h4, h5, h6, .stText {
    font-weight: 700 !important;
    text-shadow: 1px 1px 2px rgba(0,0,0,0.35);
    color: white !important;
}

/* Botones con efecto hover */
.stButton>button {
    background: linear-gradient(90deg,#6a11cb,#23a6d5);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 10px;
    transition: transform .12s ease, box-shadow .12s ease;
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}
.stButton>button:hover {
    transform: translateY(-3px) scale(1.01);
    box-shadow: 0 8px 18px rgba(0,0,0,0.25);
}

/* DataFrame: cabeceras en negrita y más naturales */
[data-testid="stDataFrame"] table thead th {
    font-weight: 700 !important;
    text-transform: none !important;
    background: rgba(0,0,0,0.15) !important;
    color: white !important;
}

/* Pequeños ajustes para inputs/expander */
.stExpander {
    background: rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 6px;
}
</style>
"""

    # --------------------------
    # Conexión a BD (crear tabla si no existe)
    # --------------------------
    crear_tabla()
    
    # --------------------------
    # Función auxiliar: exportar a Excel
    # --------------------------
    def exportar_excel(df: pd.DataFrame) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Clientes")
        return output.getvalue()

    # --------------------------
    # Encabezado
    # --------------------------
    st.markdown("<h1 style='text-align:center;'>📂 MyLocalDATA</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align:center;'>Gestor de Clientes - Agencia de Carga Internacional</h2>", unsafe_allow_html=True)

    # --------------------------
    # Formulario para registrar cliente
    # --------------------------
    with st.expander("➕ Registrar Cliente"):
        with st.form("form_cliente"):
            col1, col2, col3 = st.columns(3)
            with col1:
                nombre   = st.text_input("Nombre Cliente")
                nit      = st.text_input("NIT")
                contacto = st.text_input("Persona de Contacto")
            with col2:
                telefono = st.text_input("Teléfono")
                email    = st.text_input("Email")
                ciudad   = st.text_input("Ciudad")
            with col3:
                fecha_contacto = st.date_input("Fecha de Contacto", datetime.today())
                observacion    = st.text_area("Observación")
                contactado     = st.checkbox("Cliente Contactado")

            if st.form_submit_button("Guardar"):
                # decidir en qué base guardar: campo del formulario con selección
                destino_base = st.selectbox("Guardar en Base:", ["TRANSLOGISTIC", st.session_state.get("private_base_name", username)])
                fecha_iso = fecha_contacto.isoformat()  # YYYY-MM-DD

                datos = {
                    "nombre": nombre,
                    "nit": nit,
                    "contacto": contacto,
                    "telefono": telefono,
                    "email": email,
                    "ciudad": ciudad,
                    "fecha_contacto": fecha_iso,
                    "observacion": observacion,
                    "contactado": contactado,
                    "username": username,        # propietario del registro
                    "base_name": destino_base    # TRANSLOGISTIC o la base privada
                }

                agregar_cliente(datos)
                st.success("✅ Cliente registrado correctamente")

    # --------------------------
    # Listado y exportación de clientes
    # --------------------------
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])

    with tab1:
        # calcular filtros según sesión / admin
selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
if is_admin:
    base_filter = filtrar_base if filtrar_base and filtrar_base != "Todas" else (None if filtrar_username else None)
    # si admin filtró por base específica y no por username:
    if filtrar_base and filtrar_base != "Todas":
        df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
    elif filtrar_username:
        df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
    else:
        df_no = obtener_clientes(contactado=False, is_admin=True)
else:
    # usuario no admin: mostrar por defecto su base privada o TRANSLOGISTIC, según selección
    df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=(selected_base if selected_base != "TRANSLOGISTIC" else None))
        st.subheader("Clientes No Contactados")
        filtro = st.text_input("🔍 Buscar cliente")
        if filtro:
            df_no = df_no[df_no["nombre"].str.contains(filtro, case=False, na=False)]

        # Renombrar columnas para UI (más naturales)
def rename_columns_for_display(df):
    if df.empty:
        return df
    rename_map = {
        "nombre": "Nombre",
        "nit": "NIT",
        "contacto": "Persona de Contacto",
        "telefono": "Teléfono",
        "email": "Email",
        "ciudad": "Ciudad",
        "fecha_contacto": "Última Fecha de Contacto",
        "observacion": "Observación",
        "contactado": "Contactado",
        "username": "Propietario",
        "base_name": "Base",
        "tipo_operacion": "Tipo de Operación",
        "modalidad": "Modalidad",
        "origen": "Origen",
        "destino": "Destino",
        "mercancia": "Mercancía"
    }
    # crear copia para evitar mutar el original
    df2 = df.copy()
    df2 = df2.rename(columns={k:v for k,v in rename_map.items() if k in df2.columns})
    return df2

# ejemplo de uso justo antes de mostrar:
df_no_display = rename_columns_for_display(df_no)
        st.dataframe(df_no_display, use_container_width=True)
        if not df_no.empty:
            st.download_button(
                "⬇️ Exportar a Excel",
                data=exportar_excel(df_no),
                file_name="clientes_no_contactados.xlsx"
            )

    with tab2:
        df_si = obtener_clientes(contactado=True, username=username, is_admin=is_admin)
        st.subheader("Clientes Contactados")
        st.dataframe(df_si, use_container_width=True)
        if not df_si.empty:
            st.download_button(
                "⬇️ Exportar a Excel",
                data=exportar_excel(df_si),
                file_name="clientes_contactados.xlsx"
            )

    # --------------------------
    # Vista detallada y edición
    # --------------------------
    st.markdown("---")
    st.subheader("🔎 Vista Detallada por Cliente")

    clientes = obtener_clientes(username=username, is_admin=is_admin)
    if not clientes.empty:
        seleccion = st.selectbox("Selecciona un cliente", clientes["nombre"])
        cliente = clientes[clientes["nombre"] == seleccion].iloc[0]

        with st.form("detalle_cliente"):
            st.write(f"### {cliente['nombre']} (NIT: {cliente['nit']})")
            tipo_operacion = st.text_input("Tipo de Operación", cliente.get("tipo_operacion", ""))
            modalidad      = st.text_input("Modalidad", cliente.get("modalidad", ""))
            origen         = st.text_input("Origen", cliente.get("origen", ""))
            destino        = st.text_input("Destino", cliente.get("destino", ""))
            mercancia      = st.text_area("Mercancía", cliente.get("mercancia", ""))

            if st.form_submit_button("💾 Guardar cambios"):
                actualizar_cliente_detalle(
                    cliente["id"],
                    {
                        "tipo_operacion": tipo_operacion,
                        "modalidad":      modalidad,
                        "origen":         origen,
                        "destino":        destino,
                        "mercancia":      mercancia
                    }
                )
                st.success("✅ Información detallada actualizada")

elif st.session_state.get("authentication_status") is False:
    st.sidebar.error("❌ Usuario o contraseña incorrectos")

else:  # authentication_status es None
    st.sidebar.warning("🔑 Por favor ingresa tus credenciales")
