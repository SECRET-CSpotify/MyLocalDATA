import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from db import crear_tabla, agregar_cliente, obtener_clientes, actualizar_cliente_detalle

def normalize_credentials_from_secrets():
    creds = st.secrets.get("credentials")
    if creds:
        creds_dict = creds.to_dict()   # 👈 convierte a dict de Python
        return {"usernames": creds_dict["usernames"]}
    return None
    
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

# Convertir a un dict normal (para que sea mutable)
credentials = st.secrets["credentials"].to_dict()

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

    # --------------------------
    # Estilos personalizados
    # --------------------------
    page_bg = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Faculty+Glyphic&display=swap');
    html, body, [class*="css"] { font-family: 'Faculty Glyphic', sans-serif; }
    [data-testid="stAppViewContainer"] {
        background: linear-gradient(-45deg, #23a6d5, #23d5ab, #ff6f61, #6a11cb);
        background-size: 400% 400%;
        animation: gradientBG 15s ease infinite;
    }
    @keyframes gradientBG {
        0% {background-position: 0% 50%;}
        50% {background-position: 100% 50%;}
        100% {background-position: 0% 50%;}
    }
    h1, h2, h3, h4, h5, h6, .stText {
        font-weight: bold !important;
        text-shadow: 1px 1px 2px black;
        color: white !important;
    }
    </style>
    """
    st.markdown(page_bg, unsafe_allow_html=True)

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
                datos = {
                    "nombre": nombre,
                    "nit": nit,
                    "contacto": contacto,
                    "telefono": telefono,
                    "email": email,
                    "ciudad": ciudad,
                    "fecha_contacto": str(fecha_contacto),
                    "observacion": observacion,
                    "contactado": contactado,
                    "username": username  # <-- agrega el username actual de la sesión
                }
                agregar_cliente(datos)
                st.success("✅ Cliente registrado correctamente")

    # --------------------------
    # Listado y exportación de clientes
    # --------------------------
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])

    with tab1:
        df_no = obtener_clientes(contactado=False, username=username, is_admin=is_admin)
        st.subheader("Clientes No Contactados")
        filtro = st.text_input("🔍 Buscar cliente")
        if filtro:
            df_no = df_no[df_no["nombre"].str.contains(filtro, case=False, na=False)]
        st.dataframe(df_no, use_container_width=True)
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
