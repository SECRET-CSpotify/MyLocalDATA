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
# Autenticación
# --------------------------
# 1) Inicializar variables
name = None
authentication_status = None
username = None

# --- BLOQUE DE DIAGNÓSTICO: pega esto en lugar del bloque de autenticación ---
import streamlit as st
import streamlit_authenticator as stauth
import inspect, traceback

st.markdown("## DEBUG - diagnóstico de autenticación (temporal)")

# 1) versión y firmas
try:
    st.write("stauth version:", getattr(stauth, "__version__", "unknown"))
except Exception:
    st.write("No pude obtener stauth.__version__")

try:
    st.write("Authenticate.__init__ signature:", inspect.signature(stauth.Authenticate.__init__))
    # la función login es método de instancia, inspeccionamos la función en la clase
    st.write("Authenticate.login signature:", inspect.signature(stauth.Authenticate.login))
except Exception:
    st.write("No pude inspeccionar firmas de Authenticate.")
    st.text(traceback.format_exc())

# 2) mostrar keys en secrets y una vista segura de la estructura
try:
    st.write("Keys en st.secrets:", list(st.secrets.keys()))
    # Muestra si existe 'credentials' o 'USERS' y qué forma tienen (sin mostrar passwords)
    if "credentials" in st.secrets:
        creds = st.secrets["credentials"]
        st.write("Tipo de 'credentials':", type(creds).__name__)
        if isinstance(creds, dict):
            # si tiene 'usernames' mostramos solo los nombres
            if "usernames" in creds and isinstance(creds["usernames"], dict):
                st.write("usernames detectados en credentials:", list(creds["usernames"].keys()))
            else:
                st.write("keys en credentials (primer nivel):", list(creds.keys()))
    if "USERS" in st.secrets:
        users = st.secrets["USERS"]
        st.write("Tipo de 'USERS':", type(users).__name__)
        if isinstance(users, list):
            st.write("Longitud USERS:", len(users))
            try:
                st.write("Usernames list (USERS):", [u.get("username") for u in users if isinstance(u, dict)])
            except Exception:
                st.write("No pude listar usernames en USERS.")
except Exception:
    st.text("Error leyendo secrets:\n" + traceback.format_exc())

# 3) Normalizar credenciales (igual que antes) y probar instanciación + login con captura de errores
def normalize_credentials_from_secrets():
    creds = st.secrets.get("credentials")
    if creds:
        if isinstance(creds, dict) and "usernames" in creds:
            return creds
        if isinstance(creds, dict):
            usernames = {}
            for k, v in creds.items():
                if isinstance(v, dict) and "name" in v:
                    usernames[k] = {"name": v.get("name"), "email": v.get("email"), "password": v.get("password")}
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
            usernames[uname] = {"name": u.get("name"), "email": u.get("email"), "password": u.get("password")}
        return {"usernames": usernames}

    return None

credentials = normalize_credentials_from_secrets()
if credentials is None:
    st.error("No se detectaron credenciales válidas en st.secrets ('credentials' o 'USERS').")
    st.stop()

st.write("DEBUG: credenciales normalizadas - usernames:", list(credentials.get("usernames", {}).keys()))

# Cargar cookies/expiry (validar existencia)
missing = []
for key in ("COOKIE_NAME", "COOKIE_KEY", "COOKIE_EXPIRY_DAYS"):
    if key not in st.secrets:
        missing.append(key)
if missing:
    st.error("Faltan estas keys en st.secrets: " + ", ".join(missing))
    st.stop()

cookie_name = st.secrets["COOKIE_NAME"]
cookie_key = st.secrets["COOKIE_KEY"]
try:
    cookie_expiry = int(st.secrets["COOKIE_EXPIRY_DAYS"])
except Exception:
    st.error("COOKIE_EXPIRY_DAYS no es un entero válido.")
    st.stop()

# Intentar crear authenticator y llamar login con captura de excepciones
try:
    authenticator = stauth.Authenticate(credentials, cookie_name, cookie_key, cookie_expiry)
    st.write("Authenticator creado OK.")
except Exception:
    st.error("Error al crear authenticator — traza completa abajo:")
    st.text(traceback.format_exc())
    st.stop()

try:
    # Llamada a login envuelta para capturar cualquier TypeError u otro
    name, authentication_status, username = authenticator.login(location="sidebar")
    st.write("login() devolvió:", {"name": name, "authentication_status": authentication_status, "username": username})
except Exception:
    st.error("Error al ejecutar authenticator.login() — traza completa abajo:")
    st.text(traceback.format_exc())
    st.stop()

# indica admin (solo como info)
is_admin = username == "admin"
st.write("is_admin (username == 'admin') =>", is_admin)
# --- fin del bloque de diagnóstico ---

df_no = obtener_clientes(contactado=False, username=username, is_admin=is_admin)


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