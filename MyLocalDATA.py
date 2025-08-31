import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from db import crear_tabla, agregar_cliente, obtener_clientes, actualizar_cliente_detalle
from collections.abc import Mapping
import traceback

# --------------------------
# Configuración general
# --------------------------
st.set_page_config(page_title="Gestor de Clientes", layout="wide")

# --------------------------
# Normalizar y validar credentials desde secrets (una sola definición)
# --------------------------
# --------------------------
# Construir una copia MUTABLE de los credentials guardados en secrets
# --------------------------
from collections.abc import Mapping

def build_mutable_credentials_from_secrets():
    """
    Toma st.secrets['credentials'] (Mapping/TOML) y crea un dict Python puro:
    {'usernames': { 'user1': {'name':..., 'email':..., 'password':..., 'is_admin':...}, ... }}
    Esto evita que streamlit_authenticator intente escribir sobre st.secrets (inmutable).
    """
    raw = st.secrets.get("credentials")
    if not raw:
        return None

    # si ya viene como {'usernames': {...}} usar esa sección, si no convertir el mapping entero
    if isinstance(raw, Mapping) and "usernames" in raw and isinstance(raw["usernames"], Mapping):
        raw_usernames = raw["usernames"]
    else:
        raw_usernames = dict(raw)

    mutable_usernames = {}
    for uname, udata in dict(raw_usernames).items():
        if isinstance(udata, Mapping):
            mutable_usernames[uname] = {
                "name": udata.get("name"),
                "email": udata.get("email"),
                "password": udata.get("password"),
                "is_admin": udata.get("is_admin", False)
            }
    return {"usernames": mutable_usernames}

# Crear la copia mutable que pasaremos a streamlit_authenticator
credentials_for_auth = build_mutable_credentials_from_secrets()
if credentials_for_auth is None:
    st.error("Formato inválido en st.secrets['credentials']. Debe contener usuarios.")
    st.stop()

# --------------------------
# Validar cookies (igual que antes)
# --------------------------
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

# --------------------------
# Crear el authenticator con el dict MUTABLE
# --------------------------
try:
    authenticator = stauth.Authenticate(
        credentials_for_auth,     # <-- PASAR AQUI el dict MUTABLE (no st.secrets)
        cookie_name,
        cookie_key,
        cookie_expiry
    )
except Exception as e:
    st.error(f"Error creando stauth.Authenticate: {e}")
    st.stop()

# login (usa session_state internamente)
authenticator.login(location="sidebar")

# --------------------------
# Manejo del status de autenticación
# --------------------------
if st.session_state.get("authentication_status") is True:
    name = st.session_state.get("name")
    username = st.session_state.get("username")
    # determinar is_admin desde credentials_for_auth si existe
    is_admin = False
    try:
        is_admin = bool(credentials_for_auth.get("usernames", {}).get(username, {}).get("is_admin", False))
    except Exception:
        is_admin = (username == "admin")

    st.sidebar.success(f"Bienvenido, {name} 👋")
    authenticator.logout("Cerrar sesión", "sidebar", key="logout_button")

    # --------------------------
    # Sidebar: Bases y filtros (si admin verá opciones adicionales)
    # --------------------------
    from db import crear_tabla, agregar_cliente, obtener_clientes, actualizar_cliente_detalle, \
        set_display_base_name, get_display_base_name, eliminar_cliente, agendar_visita, obtener_visitas, agregar_contacto, obtener_contactos
    
    with st.sidebar.expander("Mi Base y Preferencias"):
        # leer display guardado en DB (si existe)
        default_private_name = f"{name}_PRIVADA" if name else f"{username}_PRIVADA"
        saved_display = None
        try:
            saved_display = get_display_base_name(username)
        except Exception:
            saved_display = None
    
        private_base_name = st.text_input("Nombre de tu base privada",
                                         value=st.session_state.get("private_base_name", saved_display or default_private_name))
        st.session_state["private_base_name"] = private_base_name
    
        # Botón para persistir el nombre personalizado
        if st.button("💾 Guardar nombre de mi base"):
            # guardar en tabla users y feedback
            try:
                set_display_base_name(username, private_base_name)
                st.success("Nombre de base guardado correctamente ✅")
            except Exception as e:
                st.error(f"No se pudo guardar el nombre de la base: {e}")
    
        # selected view: mostrar TRANSLOGISTIC o el display (pero deberemos convertirlo internamente al formato username__display)
        selected_base_view = st.radio("¿Qué base quieres ver/usar por defecto?",
                                     ["TRANSLOGISTIC", private_base_name])
        st.session_state["selected_base_view"] = selected_base_view

    # Admin filters
    if is_admin:
        st.sidebar.markdown("**Panel Admin — filtros**")
        todas = obtener_clientes()  # para listar bases disponibles; si DB grande ajustar
        bases_disponibles = []
        if not todas.empty and "base_name" in todas.columns:
            bases_disponibles = sorted(todas['base_name'].dropna().unique().tolist())
        bases_disponibles = ["TRANSLOGISTIC"] + [b for b in bases_disponibles if b != "TRANSLOGISTIC"]
        filtrar_base = st.sidebar.selectbox("Filtrar por base (Admin)", options=["Todas"] + bases_disponibles, index=0)
        filtrar_username = st.sidebar.text_input("Filtrar por username (dejar en blanco = todos)")
    else:
        filtrar_base = None
        filtrar_username = None

    # --------------------------
    # Estilos personalizados (usa Google Font disponible: Poppins)
    # --------------------------
    page_bg = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');

    :root { --main-font: 'Poppins', sans-serif; }

    html, body, [class*="css"], .stMarkdown, .stText, .stDataFrame, table {
        font-family: var(--main-font) !important;
    }

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

    h1, h2, h3, h4, h5, h6, .stText {
        font-weight: 700 !important;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.35);
        color: white !important;
    }

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

    [data-testid="stDataFrame"] table thead th {
        font-weight: 700 !important;
        text-transform: none !important;
        background: rgba(0,0,0,0.15) !important;
        color: white !important;
    }

    .stExpander {
        background: rgba(255,255,255,0.06);
        border-radius: 8px;
        padding: 6px;
    }
    </style>
    """
    st.markdown(page_bg, unsafe_allow_html=True)

    # --------------------------
    # Conexión a BD (crear tabla si no existe)
    # --------------------------
    crear_tabla()

    # --------------------------
    # Funciones auxiliares locales
    # --------------------------
    def exportar_excel(df: pd.DataFrame) -> bytes:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Clientes")
        return output.getvalue()

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
        df2 = df.copy()
        df2 = df2.rename(columns={k: v for k, v in rename_map.items() if k in df2.columns})
        return df2

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
                direccion = st.text_input("Dirección")  # campo Dirección agregado
            with col3:
                contactado = st.checkbox("Cliente Contactado")
                # Mostrar fecha solo si contactado == True
                fecha_contacto = None
                if contactado:
                    fecha_contacto = st.date_input("Fecha de Contacto", datetime.today())
                observacion = st.text_area("Observación")
    
            # <-- Guardar en Base aparece antes del botón
            # Mostrar las opciones: TRANSLOGISTIC o la base privada del usuario (mostramos display)
            display_private = st.session_state.get("private_base_name", f"{username}_PRIVADA")
            destino_base_display = st.selectbox("Guardar en Base:", ["TRANSLOGISTIC", display_private])
    
            if st.form_submit_button("Guardar"):
                # Convertir destino_display a valor interno (TRANSLOGISTIC o username__display)
                if destino_base_display == "TRANSLOGISTIC":
                    destino_base_internal = "TRANSLOGISTIC"
                else:
                    destino_base_internal = f"{username}__{destino_base_display}"
    
                fecha_iso = fecha_contacto.isoformat() if fecha_contacto else None
    
                datos = {
                    "nombre": nombre,
                    "nit": nit,
                    "contacto": contacto,
                    "telefono": telefono,
                    "email": email,
                    "ciudad": ciudad,
                    "direccion": direccion,
                    "fecha_contacto": fecha_iso,
                    "observacion": observacion,
                    "contactado": contactado,
                    "username": username,
                    "base_name": destino_base_internal
                }
    
                try:
                    agregar_cliente(datos)
                    st.success("✅ Cliente registrado correctamente")
                except Exception as e:
                    st.error("❌ Error guardando cliente. Revisa la información y los logs.")
                    st.text(str(e))
                    st.text(traceback.format_exc())

    # --------------------------
    # Listado y exportación de clientes
    # --------------------------
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])

    with tab1:
        st.subheader("Clientes No Contactados")
        # calcular filtros según sesión / admin
        selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
        if is_admin:
            if filtrar_base and filtrar_base != "Todas":
                df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
            elif filtrar_username:
                df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
            else:
                df_no = obtener_clientes(contactado=False, is_admin=True)
        else:
            # usuario no admin: mostrar por defecto su base privada o TRANSLOGISTIC, según selección
            base_arg = None if selected_base == "TRANSLOGISTIC" else selected_base
            df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=base_arg)

        filtro = st.text_input("🔍 Buscar cliente (filtra por Nombre)")
        if filtro and not df_no.empty and "nombre" in df_no.columns:
            df_no = df_no[df_no["nombre"].str.contains(filtro, case=False, na=False)]

        from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
        
        df_no_display = rename_columns_for_display(df_no)
        
        if df_no_display is None or df_no_display.empty:
            st.info("No hay clientes para mostrar.")
        else:
            gb = GridOptionsBuilder.from_dataframe(df_no_display)
            # Habilitar filtros y edición por columna (editable solo las columnas no-iden)
            gb.configure_default_column(filterable=True, editable=False, sortable=True, resizable=True)
            # Si quieres permitir edición en algunas columnas:
            editable_cols = ["Observación", "Teléfono", "Email"]  # ejemplo, solo editar campo observación/teléfono/email
            for c in editable_cols:
                if c in df_no_display.columns:
                    gb.configure_column(c, editable=True)
            gb.configure_selection(selection_mode="multiple", use_checkbox=True)
            gridOptions = gb.build()
        
            grid_response = AgGrid(
                df_no_display,
                gridOptions=gridOptions,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                height=400
            )
        
            # Descarga Excel de los datos filtrados (usar df_no, que tiene columnas originales)
            if st.button("⬇️ Exportar a Excel"):
                st.download_button(
                    "Descargar clientes no contactados (.xlsx)",
                    data=exportar_excel(df_no),
                    file_name="clientes_no_contactados.xlsx"
                )


       from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
    
    with tab2:
        st.subheader("Clientes Contactados")
    
        # 'df_si' debe venir de la lógica previa (admin vs user)
        # Si no existe o está vacío, mostramos mensaje
        if df_si is None or df_si.empty:
            st.info("No hay clientes contactados para mostrar.")
        else:
            # Preparamos la versión para visualización (columnas renombradas)
            df_si_display = rename_columns_for_display(df_si)
    
            # Construir opciones de AgGrid
            gb2 = GridOptionsBuilder.from_dataframe(df_si_display)
            # Habilitar filtros y sorting por columna
            gb2.configure_default_column(filterable=True, sortable=True, resizable=True)
            # Marcar columnas que queremos permitir editar (ejemplo: Observación, Teléfono, Email)
            editable_cols = ["Observación", "Teléfono", "Email"]
            for c in editable_cols:
                if c in df_si_display.columns:
                    gb2.configure_column(c, editable=True)
    
            # Multiselección con checkboxes
            gb2.configure_selection(selection_mode="multiple", use_checkbox=True)
            gridOptions2 = gb2.build()
    
            # Mostrar la grilla
            grid_response2 = AgGrid(
                df_si_display,
                gridOptions=gridOptions2,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                height=420
            )
    
            # Botón para exportar los datos (usa el df original 'df_si' para mantener nombres de columna de DB)
            col_dl, col_actions = st.columns([1, 1])
            with col_dl:
                if st.button("⬇️ Exportar Contactados a Excel"):
                    st.download_button(
                        "Descargar clientes contactados (.xlsx)",
                        data=exportar_excel(df_si),  # usa tu función exportar_excel existente
                        file_name="clientes_contactados.xlsx"
                    )
    
            # Acciones sobre filas seleccionadas
            selected = grid_response2.get("selected_rows", [])
            if selected:
                st.markdown(f"**Filas seleccionadas:** {len(selected)}")
                # ejemplo: mostrar botones de acción sobre las filas seleccionadas
                if st.button("🗑️ Eliminar seleccionados"):
                    st.warning("Confirmar: se eliminarán los clientes seleccionados.")
                    if st.button("Confirmar eliminación seleccionados"):
                        # Aquí deberías iterar por cada selected y llamar a eliminar_cliente(id)
                        # Asegúrate que la grilla incluya la columna 'id' para identificar registros.
                        try:
                            for row in selected:
                                rid = row.get("id")
                                if rid:
                                    eliminar_cliente(rid)
                            st.success("Clientes seleccionados eliminados ✅")
                        except Exception as e:
                            st.error(f"No se pudieron eliminar: {e}")
    
            # --- OPCIONAL: Persistir cambios editados en la DB ---
            # grid_response2['data'] contiene la tabla tal como quedó tras edición en AgGrid.
            # Para persistir cambios necesitas comparar con df_si_display y ejecutar UPDATEs.
            # Aquí te dejo un ejemplo sencillo (descomentarlo solo si deseas usarlo):
            #
            # if st.button("💾 Aplicar cambios editados"):
            #     edited_df = pd.DataFrame(grid_response2['data'])
            #     # Asegúrate de que 'id' esté presente en edited_df para mapear a la tabla DB
            #     for _, row in edited_df.iterrows():
            #         rid = row.get("id")
            #         if not rid:
            #             continue
            #         # Construir dict con columnas que quieras actualizar (usar nombres de DB, no los renombrados)
            #         # Ej: si en rename_columns_for_display "Observación" corresponde a "observacion"
            #         updates = {}
            #         if "Observación" in row.index:
            #             updates["observacion"] = row["Observación"]
            #         if "Teléfono" in row.index:
            #             updates["telefono"] = row["Teléfono"]
            #         if "Email" in row.index:
            #             updates["email"] = row["Email"]
            #         if updates:
            #             # ejecuta un UPDATE directo (debes implementar una función en db.py o usar engine)
            #             # ejemplo rápido (requiere importar 'engine' y 'text' desde db.py):
            #             with engine.begin() as conn:
            #                 stmt = text("""
            #                     UPDATE clientes SET
            #                         telefono = COALESCE(:telefono, telefono),
            #                         email = COALESCE(:email, email),
            #                         observacion = COALESCE(:observacion, observacion)
            #                     WHERE id = :id
            #                 """)
            #                 params = {"id": rid, "telefono": updates.get("telefono"), "email": updates.get("email"), "observacion": updates.get("observacion")}
            #                 conn.execute(stmt, params)
            #     st.success("Cambios aplicados a la base de datos.")

    # --------------------------
    # Vista detallada y edición
    # --------------------------
    st.markdown("---")
    st.subheader("🔎 Vista Detallada por Cliente")

    # Obtener clientes para selector (para admin respetar filtros)
    if is_admin:
        clientes = obtener_clientes(is_admin=True)
    else:
        base_arg = None if st.session_state.get("selected_base_view", "TRANSLOGISTIC") == "TRANSLOGISTIC" else st.session_state.get("selected_base_view")
        clientes = obtener_clientes(username=username, is_admin=False, base_name=base_arg)

if clientes is not None and not clientes.empty:
    seleccion = st.selectbox("Selecciona un cliente", clientes["nombre"].tolist())
    cliente = clientes[clientes["nombre"] == seleccion].iloc[0]

    with st.form("detalle_cliente"):
        st.write(f"### {cliente.get('nombre', '')} (NIT: {cliente.get('nit', '')})")
        tipo_operacion = st.text_input("Tipo de Operación", cliente.get("tipo_operacion", ""))
        modalidad = st.text_input("Modalidad", cliente.get("modalidad", ""))
        origen = st.text_input("Origen", cliente.get("origen", ""))
        destino = st.text_input("Destino", cliente.get("destino", ""))
        mercancia = st.text_area("Mercancía", cliente.get("mercancia", ""))

        col_a, col_b = st.columns([1,1])
        with col_a:
            if st.form_submit_button("💾 Guardar cambios"):
                actualizar_cliente_detalle(
                    cliente["id"],
                    {
                        "tipo_operacion": tipo_operacion,
                        "modalidad": modalidad,
                        "origen": origen,
                        "destino": destino,
                        "mercancia": mercancia
                    }
                )
                st.success("✅ Información detallada actualizada")

        with col_b:
            # Botón eliminar (inicia confirmación)
            if st.button("🗑️ Eliminar cliente"):
                st.warning("Estás a punto de eliminar este cliente. Esta acción es irreversible.")
                if st.button("Confirmar eliminación"):
                    try:
                        eliminar_cliente(cliente["id"])
                        st.success("Cliente eliminado ✅")
                    except Exception as e:
                        st.error(f"No se pudo eliminar el cliente: {e}")

    # -------------------------
    # Historial de contactos
    # -------------------------
    st.markdown("#### 📞 Historial de Contactos")
    contactos_df = obtener_contactos(cliente["id"])
    if contactos_df is None or contactos_df.empty:
        st.info("No hay registros de contactos todavía.")
    else:
        # renombrar columnas si quieres
        st.dataframe(contactos_df, use_container_width=True)

    # Formulario para agregar nuevo contacto al historial
    with st.form("agregar_contacto"):
        col1, col2 = st.columns(2)
        with col1:
            fecha_contacto = st.date_input("Fecha contacto", datetime.today())
            tipo_contacto = st.selectbox("Tipo", ["Presencial", "Llamada", "Email"])
        with col2:
            notas_contacto = st.text_area("Notas (opcional)")
        if st.form_submit_button("Agregar contacto"):
            try:
                agregar_contacto(cliente["id"], fecha_contacto.isoformat(), tipo_contacto, notas_contacto)
                st.success("Contacto agregado al historial ✅")
            except Exception as e:
                st.error(f"No se pudo agregar el contacto: {e}")

    # -------------------------
    # Agenda de visitas
    # -------------------------
    st.markdown("#### 📅 Agenda de Visitas")
    with st.form("agendar_visita"):
        fecha_visita = st.date_input("Fecha de visita")
        medio_visita = st.selectbox("Medio", ["Presencial", "Llamada", "Email"])
        if st.form_submit_button("Programar visita"):
            try:
                agendar_visita(cliente["id"], fecha_visita.isoformat(), medio_visita, username)
                st.success(f"Visita programada para {fecha_visita.isoformat()}")
            except Exception as e:
                st.error(f"No se pudo programar la visita: {e}")

    visitas_df = obtener_visitas(cliente["id"])
    if visitas_df is None or visitas_df.empty:
        st.info("No hay visitas agendadas.")
    else:
        st.dataframe(visitas_df, use_container_width=True)


elif st.session_state.get("authentication_status") is False:
    st.sidebar.error("❌ Usuario o contraseña incorrectos")

else:  # authentication_status es None
    st.sidebar.warning("🔑 Por favor ingresa tus credenciales")
