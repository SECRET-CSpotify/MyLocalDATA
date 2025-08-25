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
# --------------------------
# Configuración general
# --------------------------
st.set_page_config(page_title="Gestor de Clientes", layout="wide")

# --------------------------
# Autenticación
with open("auth_config.yaml") as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config['credentials'],
    config['cookie']['name'],
    config['cookie']['key'],
    config['cookie']['expiry_days'],
)

# login devuelve un diccionario o None
# Renderizar formulario de login en sidebar
authenticator.login("Iniciar Sesión", "sidebar")

# Comprobar el estado de autenticación
authentication_status = st.session_state.get("authentication_status")
name = st.session_state.get("name")
username = st.session_state.get("username")

st.write("DEBUG authentication_status:", authentication_status)
st.write("DEBUG name:", name)
st.write("DEBUG username:", username)

if login_info is not None:
    authentication_status = login_info.get("authentication_status")
    name = login_info.get("name")
    username = login_info.get("username")
else:
    authentication_status = None
    name = None
    username = None

# Control de flujo de acceso
if authentication_status:
    st.sidebar.success(f"Bienvenido, {name} 👋")
    authenticator.logout("Cerrar sesión", "sidebar")
    
    # ⬇️ Todo el resto de tu aplicación va dentro de este bloque
    # Fondo animado y tipografía
    page_bg = """
    <style>
    /* Importar fuente */
    @import url('https://fonts.googleapis.com/css2?family=Faculty+Glyphic&display=swap');

    html, body, [class*="css"] {
        font-family: 'Faculty Glyphic', sans-serif;
    }

    /* Fondo animado */
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

    /* Estilo de títulos */
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
    # Funciones auxiliares
    # --------------------------
    def exportar_excel(df):
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
                nombre = st.text_input("Nombre Cliente")
                nit = st.text_input("NIT")
                contacto = st.text_input("Persona de Contacto")
            with col2:
                telefono = st.text_input("Teléfono")
                email = st.text_input("Email")
                ciudad = st.text_input("Ciudad")
            with col3:
                fecha_contacto = st.date_input("Fecha de Contacto", datetime.today())
                observacion = st.text_area("Observación")
                contactado = st.checkbox("Cliente Contactado")

            submitted = st.form_submit_button("Guardar")
            if submitted:
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
                agregar_cliente(datos)
                st.success("✅ Cliente registrado correctamente")

    # --------------------------
    # Tablas de clientes
    # --------------------------
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])

    with tab1:
        df_no = obtener_clientes(contactado=False)
        st.subheader("Clientes No Contactados")
        filtro = st.text_input("🔍 Buscar cliente")
        if filtro:
            df_no = df_no[df_no["nombre"].str.contains(filtro, case=False, na=False)]
        st.dataframe(df_no, use_container_width=True)

        if not df_no.empty:
            st.download_button("⬇️ Exportar a Excel", data=exportar_excel(df_no),
                            file_name="clientes_no_contactados.xlsx")

    with tab2:
        df_si = obtener_clientes(contactado=True)
        st.subheader("Clientes Contactados")
        st.dataframe(df_si, use_container_width=True)

        if not df_si.empty:
            st.download_button("⬇️ Exportar a Excel", data=exportar_excel(df_si),
                            file_name="clientes_contactados.xlsx")

    # --------------------------
    # Vista detallada
    # --------------------------
    st.markdown("---")
    st.subheader("🔎 Vista Detallada por Cliente")

    clientes = obtener_clientes()
    if not clientes.empty:
        seleccion = st.selectbox("Selecciona un cliente", clientes["nombre"])
        cliente = clientes[clientes["nombre"] == seleccion].iloc[0]

        with st.form("detalle_cliente"):
            st.write(f"### {cliente['nombre']} (NIT: {cliente['nit']})")
            tipo_op = st.text_input("Tipo de Operación", cliente["tipo_operacion"] or "")
            modalidad = st.text_input("Modalidad", cliente["modalidad"] or "")
            origen = st.text_input("Origen", cliente["origen"] or "")
            destino = st.text_input("Destino", cliente["destino"] or "")
            mercancia = st.text_area("Mercancía", cliente["mercancia"] or "")
            guardar = st.form_submit_button("💾 Guardar cambios")
            if guardar:
                actualizar_cliente_detalle(
                    cliente["id"],
                    {
                        "tipo_op": tipo_op,
                        "modalidad": modalidad,
                        "origen": origen,
                        "destino": destino,
                        "mercancia": mercancia
                    }
                )
                st.success("✅ Información detallada actualizada")

elif authentication_status is False:
    st.error("❌ Usuario o contraseña incorrectos")
elif authentication_status is None:
    st.warning("🔑 Por favor ingresa tus credenciales")
