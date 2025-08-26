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

# 2) Cargar configuración de autenticación
# --- bloque robusto de autenticación (reemplaza el tuyo) ---
import streamlit as st
import streamlit_authenticator as stauth
import traceback

def normalize_credentials_from_secrets():
    """
    Devuelve un objeto 'credentials' listo para pasar a stauth.Authenticate.
    Acepta dos formatos comunes en Streamlit secrets:
      1) Lista: [[USERS]] -> st.secrets["USERS"]  (lista de dicts con 'username')
      2) Diccionario: [credentials.usernames.<user>] -> st.secrets["credentials"]
    """
    # Intenta obtener la forma recomendada primero
    creds = st.secrets.get("credentials")
    if creds:
        # Si ya viene como credentials con 'usernames', devolverlo tal cual
        if isinstance(creds, dict) and "usernames" in creds:
            return creds
        # Si creds es un dict pero no tiene 'usernames', podría estar en forma [credentials.<user>]
        # Convertir a { "usernames": { username: {name,email,password} } }
        if isinstance(creds, dict):
            usernames = {}
            for k, v in creds.items():
                # v debería contener name, email, password
                if isinstance(v, dict) and "name" in v:
                    usernames[k] = {
                        "name": v.get("name"),
                        "email": v.get("email"),
                        "password": v.get("password"),
                    }
            return {"usernames": usernames}

    # Si no hay 'credentials', revisa si vienen como lista [[USERS]]
    users_list = st.secrets.get("USERS")
    if users_list and isinstance(users_list, list):
        usernames = {}
        for u in users_list:
            # cada 'u' = dict con keys username, name, email, password
            uname = u.get("username") or u.get("name")
            if not uname:
                continue
            usernames[uname] = {
                "name": u.get("name"),
                "email": u.get("email"),
                "password": u.get("password"),
            }
        return {"usernames": usernames}

    # Si llegamos aquí, no encontramos credenciales en un formato conocido
    return None

# DEBUG seguro: mostrar solo estructura y nombres de usuario (no valores sensibles)
try:
    st.write("DEBUG: keys in st.secrets ->", list(st.secrets.keys()))
    creds_candidate = st.secrets.get("credentials") or st.secrets.get("USERS")
    st.write("DEBUG: credentials present?:", creds_candidate is not None)
    if isinstance(creds_candidate, dict):
        st.write("DEBUG: credentials keys:", list(creds_candidate.keys()))
    elif isinstance(creds_candidate, list):
        st.write("DEBUG: USERS list length:", len(creds_candidate))
        st.write("DEBUG: USERS usernames:", [u.get("username") for u in creds_candidate if isinstance(u, dict)])
except Exception:
    st.text("DEBUG read error:\n" + traceback.format_exc())

# Normalizar
credentials = normalize_credentials_from_secrets()
if credentials is None:
    st.error("No se encontraron credenciales válidas en Streamlit Secrets. Revisa el formato (usa 'credentials' con 'usernames' o 'USERS' lista).")
    st.stop()

# muestra sólo los usernames para confirmar
try:
    st.write("DEBUG: detected usernames:", list(credentials.get("usernames", {}).keys()))
except Exception:
    st.write("DEBUG: unable to list usernames")

# Cargar cookies/expiry
try:
    cookie_name = st.secrets["COOKIE_NAME"]
    cookie_key = st.secrets["COOKIE_KEY"]
    cookie_expiry = int(st.secrets.get("COOKIE_EXPIRY_DAYS", 30))
except Exception:
    st.error("Faltan secrets de cookies (COOKIE_NAME/COOKIE_KEY/COOKIE_EXPIRY_DAYS).")
    st.stop()

# Instanciar Authenticate con manejo de error para mostrar la traza real
try:
    authenticator = stauth.Authenticate(
        credentials,  # debe tener la estructura {"usernames": {...}}
        cookie_name,
        cookie_key,
        cookie_expiry
    )
except Exception as e:
    st.error("Error al instanciar stauth.Authenticate — muestro traza:")
    st.text(traceback.format_exc())
    st.stop()

# Login (capturar excepción para ver la traza completa)
try:
    name, authentication_status, username = authenticator.login(location="sidebar")
except Exception as e:
    st.error("Error en authenticator.login() — muestro traza completa:")
    st.text(traceback.format_exc())
    st.stop()

# identifica admin de forma flexible
is_admin = False
if username:
    is_admin = (username == "admin") or (username == st.secrets.get("ADMIN_USER"))

# --- fin del bloque ---


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
                    "contactado": contactado
                }
                # Añadir username al diccionario de datos
                agregar_cliente({**datos, "username": username})
                st.success("✅ Cliente registrado correctamente")

    # --------------------------
    # Listado y exportación de clientes
    # --------------------------
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])
    ALTER TABLE clientes ADD COLUMN username TEXT NOT NULL;

    with tab1:
        df_no = obtener_clientes(contactado=False)
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
        df_si = obtener_clientes(contactado=True)
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

    clientes = obtener_clientes()
    if not clientes.empty:
        seleccion = st.selectbox("Selecciona un cliente", clientes["nombre"])
        cliente   = clientes[clientes["nombre"] == seleccion].iloc[0]

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