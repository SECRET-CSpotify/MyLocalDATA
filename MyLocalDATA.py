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
import streamlit as st
import streamlit_authenticator as stauth
import traceback
from collections.abc import Mapping

def normalize_credentials_from_secrets():
    """
    Devuelve un objeto {'usernames': {...}} listo para pasar a stauth.Authenticate.
    Acepta:
      - st.secrets['credentials'] en forma de mapping (AttrDict/dict) con 'usernames' o con usuarios como subkeys.
      - st.secrets['USERS'] como lista de dicts con clave 'username'.
    """
    creds = st.secrets.get("credentials")
    # 1) Si existe 'credentials'
    if creds:
        # Si es Mapping (incluye AttrDict), convertir a dict para manejo seguro
        if isinstance(creds, Mapping):
            # caso ideal: ya viene con key "usernames"
            if "usernames" in creds and isinstance(creds["usernames"], Mapping):
                # ya está en la forma correcta
                return {"usernames": dict(creds["usernames"])}
            # si no tiene 'usernames', interpretamos que creds tiene usuario como keys
            usernames = {}
            for k, v in dict(creds).items():
                # v puede ser AttrDict o dict-like
                if isinstance(v, Mapping) and ("name" in v or "email" in v or "password" in v):
                    usernames[k] = {
                        "name": v.get("name"),
                        "email": v.get("email"),
                        "password": v.get("password")
                    }
            if usernames:
                return {"usernames": usernames}
    # 2) Si no, revisar lista USERS (forma [[USERS]] en secrets)
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
    # nada válido
    return None

# --- debug seguro (muestra estructura, no contraseñas) ---
st.write("DEBUG: keys en st.secrets ->", list(st.secrets.keys()))
try:
    c = st.secrets.get("credentials")
    st.write("DEBUG: tipo de credentials ->", type(c).__name__)
    if isinstance(c, Mapping):
        st.write("DEBUG: keys top-level de credentials ->", list(dict(c).keys()))
except Exception:
    st.text("DEBUG lectura credentials:\n" + traceback.format_exc())

credentials = normalize_credentials_from_secrets()
if credentials is None:
    st.error("No se detectaron credenciales válidas en st.secrets. Asegúrate del formato (ver ejemplo).")
    st.stop()

st.write("DEBUG: usernames detectados ->", list(credentials.get("usernames", {}).keys()))

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

# Instanciar Authenticate (capturar errores)
try:
    users = credentials
    authenticator = stauth.Authenticate(users, cookie_name, cookie_key, cookie_expiry, auto_hash=False)

    st.write("DEBUG: authenticator instanciado OK")
except Exception:
    st.error("Error creando stauth.Authenticate; muestro traza:")
    st.text(traceback.format_exc())
    st.stop()

# Login (capturamos excepciones)
try:
    login_result = authenticator.login(location="sidebar")
    if login_result is None:
        name, authentication_status, username = None, None, None
        st.write("DEBUG: login() devolvió None (no hay interacción aún)")
    else:
        name, authentication_status, username = login_result
        st.write("DEBUG: login() OK ->", {
            "name": name,
            "authentication_status": authentication_status,
            "username": username
        })
except Exception:
    st.error("Error ejecutando authenticator.login(); muestro traza:")
    st.text(traceback.format_exc())
    st.stop()

is_admin = (username == "admin") if username else False

# ------------------ fin bloque ------------------

# --------------------------
# Control de acceso
# --------------------------
if authentication_status:

    st.sidebar.success(f"Bienvenido, {name} 👋")
    authenticator.logout("Cerrar sesión", "sidebar")

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

elif authentication_status is False:
    st.sidebar.error("❌ Usuario o contraseña incorrectos")

else:  # authentication_status is None
    st.sidebar.warning("🔑 Por favor ingresa tus credenciales")