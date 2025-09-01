import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import yaml
from yaml.loader import SafeLoader
import streamlit_authenticator as stauth
from db import crear_tabla, agregar_cliente, obtener_clientes, actualizar_cliente_detalle, \
    eliminar_cliente, set_display_base_name, get_display_base_name, agendar_visita, obtener_visitas, \
    agregar_contacto, obtener_contactos, actualizar_cliente_campos, engine, text

from collections.abc import Mapping
import traceback
import time

def safe_rerun():
    """
    Intenta forzar un rerun de la app.
    - Primero intenta st.experimental_rerun() (si existe).
    - Si no existe, usa st.query_params como fallback para forzar un rerun
      (st.query_params espera valores como listas de strings, por eso convertimos).
    - Si todo falla, deja una marca en session_state para que el siguiente run lo detecte.
    """
    try:
        # intento directo (si la función existe)
        st.experimental_rerun()
        return
    except Exception:
        pass

    # fallback: cambiar query params usando la API st.query_params
    try:
        # st.query_params es un mapping parecido a {str: list[str]}
        params = dict(st.query_params)  # copia para modificar
        # actualizar la clave _refresh con timestamp (usar lista de strings)
        params["_refresh"] = [str(int(time.time()))]
        # escribir de vuelta en st.query_params (esto provoca un rerun)
        st.query_params = params
        return
    except Exception:
        pass

    # último recurso: marcar en session_state (al menos el app puede leer esto en el siguiente run)
    try:
        st.session_state["_force_refresh"] = int(time.time())
    except Exception:
        # si ni siquiera esto funciona, silenciosamente no hacemos nada más
        pass


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
    @font-face {
        font-family: 'Faculty Glyphic';
        src: url('https://fonts.gstatic.com/s/facultyglyphic/v4/RrQIbot2-iBvI2mYSyKIrcgoBuQ4Eu2EBVk.woff2') format('woff2'),
            url('https://fonts.gstatic.com/s/facultyglyphic/v4/RrQIbot2-iBvI2mYSyKIrcgoBuQ4HO2E.woff2') format('woff2');
        font-weight: 300 800;
        font-style: normal;
        font-display: swap;
    }
    
    :root { --main-font: 'Faculty Glyphic'; }

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
            "direccion": "Dirección",
            "fecha_contacto": "Última Fecha de Contacto",
            "observacion": "Observación",
            "contactado": "Contactado",
            "username": "Propietario",
            "base_name": "Base",
            "tipo_operacion": "Tipo de Operación",
            "modalidad": "Modalidad",
            "origen": "Origen",
            "destino": "Destino",
            "mercancia": "Mercancía",
            "id": "id"
        }
        df2 = df.copy()
        df2 = df2.rename(columns={k: v for k, v in rename_map.items() if k in df2.columns})
        return df2

    # --------------------------
    # Encabezado
    # --------------------------
    st.markdown("<h1 style='text-align:center;'>📂 MyLocalDATA</h1>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align:center;'>Gestor de Clientes</h2>", unsafe_allow_html=True)

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
    # Listado y exportación de clientes (AgGrid con guardado automático)
    # --------------------------
    # --------------------------
    # Cargar df_no / df_si (con caché en session_state y soporte de "force refresh")
    # --------------------------
    # Intentar usar versiones en caché si existen (para respuesta inmediata)
    df_no = st.session_state.get('df_no_cached')
    df_si = st.session_state.get('df_si_cached')
    
    # Flag que puede forzar recarga desde la BD (safe_rerun() podía setear esto)
    force_refresh = False
    if st.session_state.get("_force_refresh"):
        force_refresh = True
        # consumimos la marca para evitar recargas repetidas
        try:
            st.session_state.pop("_force_refresh", None)
        except Exception:
            pass
    
    # Si no hay caché o se pide recarga forzada, leer desde la BD y actualizar caché
    if df_no is None or df_si is None or force_refresh:
        selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
    
        try:
            if is_admin:
                if 'filtrar_base' in locals() and filtrar_base and filtrar_base != "Todas":
                    df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
                    df_si = obtener_clientes(contactado=True, username=None, is_admin=True, base_name=filtrar_base)
                elif 'filtrar_username' in locals() and filtrar_username:
                    df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
                    df_si = obtener_clientes(contactado=True, username=filtrar_username, is_admin=True)
                else:
                    df_no = obtener_clientes(contactado=False, is_admin=True)
                    df_si = obtener_clientes(contactado=True, is_admin=True)
            else:
                if selected_base == "TRANSLOGISTIC":
                    df_no = obtener_clientes(contactado=False, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                    df_si = obtener_clientes(contactado=True, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                else:
                    internal_base = f"{username}__{selected_base}"
                    df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=internal_base)
                    df_si = obtener_clientes(contactado=True, username=username, is_admin=False, base_name=internal_base)
    
            # Guardar en session_state para reuso por este run y futuros runs
            st.session_state['df_no_cached'] = df_no
            st.session_state['df_si_cached'] = df_si
        except Exception as e:
            st.error(f"Error al leer clientes desde la BD: {e}")
            df_no = pd.DataFrame()
            df_si = pd.DataFrame()
    
    # Import AgGrid — preferible tenerlo al top, pero lo dejamos aquí si no está importado antes
    from st_aggrid import AgGrid, GridOptionsBuilder, DataReturnMode, GridUpdateMode
    
    # Crear tabs
    tab1, tab2 = st.tabs(["📋 No Contactados", "✅ Contactados"])

    st.write("DEBUG: df_no_cached columns:", None if st.session_state.get('df_no_cached') is None else st.session_state['df_no_cached'].columns.tolist())
    st.write("DEBUG: df_si_cached columns:", None if st.session_state.get('df_si_cached') is None else st.session_state['df_si_cached'].columns.tolist())
    st.write("DEBUG: len df_no_cached:", None if st.session_state.get('df_no_cached') is None else len(st.session_state['df_no_cached']))
    st.write("DEBUG: len df_si_cached:", None if st.session_state.get('df_si_cached') is None else len(st.session_state['df_si_cached']))

    # --------------------------------------------------------------------
    # Helper: mapping display columns <-> DB columns (debe coincidir con rename_columns_for_display)
    # --------------------------------------------------------------------
    rename_map = {
        "nombre": "Nombre",
        "nit": "NIT",
        "contacto": "Persona de Contacto",
        "telefono": "Teléfono",
        "email": "Email",
        "ciudad": "Ciudad",
        "direccion": "Dirección",
        "fecha_contacto": "Última Fecha de Contacto",
        "observacion": "Observación",
        "contactado": "Contactado",
        "username": "Propietario",
        "base_name": "Base",
        "tipo_operacion": "Tipo de Operación",
        "modalidad": "Modalidad",
        "origen": "Origen",
        "destino": "Destino",
        "mercancia": "Mercancía",
        "id": "id"
    }
    # Inverso: display -> db
    display_to_db = {v: k for k, v in rename_map.items()}
    
    # ------------------------- 
    # TAB 1: NO CONTACTADOS
    # -------------------------
    with tab1:
        st.subheader("Clientes No Contactados")
    
        filtro = st.text_input("🔍 Buscar cliente (filtra por Nombre)", key="filtro_no")
        df_no_filtered = df_no.copy()
        if filtro and not df_no_filtered.empty and "nombre" in df_no_filtered.columns:
            df_no_filtered = df_no_filtered[df_no_filtered["nombre"].str.contains(filtro, case=False, na=False)]
    
        # Normalizar y preparar DF para mostrar
        df_no_display = rename_columns_for_display(df_no_filtered)
    
        # Si rename_columns_for_display eliminó 'id', lo recuperamos desde df_no_filtered
        if df_no_display is None:
            df_no_display = pd.DataFrame()
    
        if "id" not in df_no_display.columns and "id" in df_no_filtered.columns:
            try:
                df_no_display["id"] = df_no_filtered["id"].astype(int)
            except Exception:
                df_no_display["id"] = df_no_filtered["id"].astype(str)
    
        if df_no_display.empty:
            st.info("No hay clientes para mostrar.")
        else:
            # Guardamos copia original (claves como str)
            orig_no_key = "orig_no_map"
            orig_no_map = {str(r.get("id")): r for r in df_no_display.to_dict("records")}
            st.session_state[orig_no_key] = orig_no_map
    
            # Configurar AgGrid
            gb = GridOptionsBuilder.from_dataframe(df_no_display)
            gb.configure_default_column(filterable=True, editable=False, sortable=True, resizable=True)
    
            # Asegurar columna id oculta para que venga en data/resultados
            if "id" in df_no_display.columns:
                gb.configure_column("id", hide=True, editable=False)
    
            # Configurar selección por checkbox (y marcar checkboxSelection en la primera columna visible)
            gb.configure_selection(selection_mode="multiple", use_checkbox=True)
            visible_cols = [c for c in df_no_display.columns if c != "id"]
            first_col = visible_cols[0] if visible_cols else "id"
            try:
                gb.configure_column(first_col, checkboxSelection=True, headerCheckboxSelection=True)
            except Exception:
                # no crítico; use_checkbox suele bastar
                pass
    
            # Campos editables (mantener los que ya tenías)
            gb.configure_column("Nombre", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("NIT", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Persona de Contacto", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Dirección", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Ciudad", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Teléfono", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Email", editable=True, cellEditor="agTextCellEditor")
            gb.configure_column("Observación", editable=True, cellEditor="agLargeTextCellEditor")
            gb.configure_column("Última Fecha de Contacto", editable=True, cellEditor="agDateCellEditor")
            gb.configure_column("Contactado", editable=True, cellEditor="agCheckboxCellEditor")
    
            gridOptions = gb.build()
    
            grid_response = AgGrid(
                df_no_display,
                gridOptions=gridOptions,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                height=420
            )
    
            # --- Guardado automático de ediciones (igual que el bloque que ya tenías) ---
            try:
                edited = pd.DataFrame(grid_response.get("data", []))
                if not edited.empty:
                    orig_map = st.session_state.get(orig_no_key, {})
                    applied_any_update = False
    
                    for _, row in edited.iterrows():
                        rid_raw = row.get("id")
                        if rid_raw is None:
                            continue
                        try:
                            rid_str = str(int(rid_raw))
                        except Exception:
                            rid_str = str(rid_raw)
    
                        orig_row = orig_map.get(rid_str, {})
                        updates_db = {}
    
                        for disp_col in edited.columns:
                            if disp_col == "id":
                                continue
                            old_val = orig_row.get(disp_col)
                            new_val = row.get(disp_col)
                            if (pd.isna(old_val) and (new_val is not None and new_val != "")) or (not pd.isna(old_val) and old_val != new_val):
                                db_col = display_to_db.get(disp_col)
                                if not db_col:
                                    continue
    
                                # Manejo de fecha_contacto
                                if db_col == "fecha_contacto":
                                    try:
                                        if new_val in (None, "", "None", "null", "NULL"):
                                            updates_db[db_col] = None
                                        elif isinstance(new_val, str) and new_val.strip() in ("{}", "{ }"):
                                            updates_db[db_col] = None
                                        elif isinstance(new_val, dict):
                                            date_candidate = new_val.get("date") or new_val.get("value") or next(iter(new_val.values()), None)
                                            parsed = pd.to_datetime(date_candidate, errors="coerce")
                                            updates_db[db_col] = None if pd.isna(parsed) else str(parsed.date())
                                        elif hasattr(new_val, "date"):
                                            try:
                                                updates_db[db_col] = str(new_val.date())
                                            except Exception:
                                                updates_db[db_col] = None
                                        else:
                                            parsed = pd.to_datetime(new_val, errors="coerce")
                                            updates_db[db_col] = None if pd.isna(parsed) else str(parsed.date())
                                    except Exception:
                                        updates_db[db_col] = None
    
                                elif db_col == "contactado":
                                    if isinstance(new_val, bool):
                                        updates_db[db_col] = new_val
                                    else:
                                        updates_db[db_col] = bool(new_val)
                                else:
                                    updates_db[db_col] = new_val
    
                        if updates_db:
                            try:
                                try:
                                    cliente_id_param = int(rid_str)
                                except Exception:
                                    cliente_id_param = rid_str
                                actualizar_cliente_campos(cliente_id_param, updates_db)
                                applied_any_update = True
                                orig_map.setdefault(rid_str, {})
                                for k_disp, v in row.items():
                                    orig_map[rid_str][k_disp] = v
                            except Exception as e:
                                st.error(f"Error guardando cambios para id {rid_str}: {e}")
    
                    # persistimos el mapa actualizado
                    st.session_state[orig_no_key] = orig_map
                    
                    # --------- REFRESCAR INMEDIATAMENTE LOS DF desde la BD ----------
                    try:
                        # Volver a obtener los datos desde la DB usando la misma lógica que usas arriba
                        if is_admin:
                            if filtrar_base and filtrar_base != "Todas":
                                df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
                                df_si = obtener_clientes(contactado=True, username=None, is_admin=True, base_name=filtrar_base)
                            elif filtrar_username:
                                df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
                                df_si = obtener_clientes(contactado=True, username=filtrar_username, is_admin=True)
                            else:
                                df_no = obtener_clientes(contactado=False, is_admin=True)
                                df_si = obtener_clientes(contactado=True, is_admin=True)
                        else:
                            selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
                            if selected_base == "TRANSLOGISTIC":
                                df_no = obtener_clientes(contactado=False, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                                df_si = obtener_clientes(contactado=True, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                            else:
                                internal_base = f"{username}__{selected_base}"
                                df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=internal_base)
                                df_si = obtener_clientes(contactado=True, username=username, is_admin=False, base_name=internal_base)
                    
                        # Guardar en session_state para que el siguiente render use estas versiones
                        st.session_state['df_no_cached'] = df_no
                        st.session_state['df_si_cached'] = df_si
                    
                        # Mensaje opcional para debug (puedes quitarlo luego)
                        st.info(f"✅ Datos recargados: No contactados={len(df_no) if df_no is not None else 0}, Contactados={len(df_si) if df_si is not None else 0}")
                    except Exception as e:
                        st.error(f"Error refrescando datos desde BD: {e}")
                    
                    # Forzar rerun controlado para que la UI vuelva a render con los DF recargados
                    if applied_any_update:
                        safe_rerun()

    
            except Exception as e:
                st.text(f"(Aviso) Error procesando ediciones automáticas: {e}")
    
            # resto: exportar, eliminar, etc. (mantén tu lógica de eliminación pero usa safe_rerun() después)

    
            # Botón de exportar (usa df_no original sin renombrar para mantener campos DB)
            st.download_button(
                "⬇️ Exportar clientes no contactados (.xlsx)",
                data=exportar_excel(df_no_filtered),
                file_name="clientes_no_contactados.xlsx"
            )
    
            # Acciones sobre filas seleccionadas (ejemplo: eliminar)
            selected_no = grid_response.get("selected_rows", [])
            # Evitar truthiness ambigua de pandas.DataFrame: comprobar explícitamente longitud
            if selected_no is not None and len(selected_no) > 0:
                st.markdown(f"**Filas seleccionadas:** {len(selected_no)}")
                if st.button("🗑️ Eliminar seleccionados (No Contactados)", key="eliminar_no"):
                    st.warning("Confirmar: se eliminarán los clientes seleccionados.")
                    if st.button("Confirmar eliminación seleccionados (No Contactados)", key="confirm_eliminar_no"):
                        try:
                            deleted_any = False
                            for row in selected_no:
                                if hasattr(row, "to_dict"):
                                    row = row.to_dict()
                                rid = row.get("id")
                                if not rid:
                                    continue
                                try:
                                    eliminar_cliente(int(rid))
                                    deleted_any = True
                                except Exception as e:
                                    st.error(f"No se pudo eliminar id {rid}: {e}")
                            if deleted_any:
                                st.success("Clientes seleccionados eliminados ✅")
                                # Releer la BD inmediatamente y guardar en session_state
                                try:
                                    # Reusar la misma lógica para recomponer df_no y df_si
                                    if is_admin:
                                        if filtrar_base and filtrar_base != "Todas":
                                            df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
                                            df_si = obtener_clientes(contactado=True, username=None, is_admin=True, base_name=filtrar_base)
                                        elif filtrar_username:
                                            df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
                                            df_si = obtener_clientes(contactado=True, username=filtrar_username, is_admin=True)
                                        else:
                                            df_no = obtener_clientes(contactado=False, is_admin=True)
                                            df_si = obtener_clientes(contactado=True, is_admin=True)
                                    else:
                                        selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
                                        if selected_base == "TRANSLOGISTIC":
                                            df_no = obtener_clientes(contactado=False, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                                            df_si = obtener_clientes(contactado=True, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                                        else:
                                            internal_base = f"{username}__{selected_base}"
                                            df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=internal_base)
                                            df_si = obtener_clientes(contactado=True, username=username, is_admin=False, base_name=internal_base)
                            
                                    st.session_state['df_no_cached'] = df_no
                                    st.session_state['df_si_cached'] = df_si
                                except Exception as e:
                                    st.error(f"Error refrescando datos tras eliminación: {e}")
                            
                                # Forzar rerun controlado para que la UI se actualice
                                safe_rerun()

                            else:
                                st.info("No se eliminaron registros.")
                        except Exception as e:
                            st.error(f"No se pudieron eliminar: {e}")

    
    # -------------------------
    # TAB 2: CONTACTADOS
    # -------------------------
    with tab2:
        st.subheader("Clientes Contactados")
    
        filtro2 = st.text_input("🔍 Buscar cliente (Contactados)", key="filtro_si")
        df_si_filtered = df_si.copy()
        if filtro2 and not df_si_filtered.empty and "nombre" in df_si_filtered.columns:
            df_si_filtered = df_si_filtered[df_si_filtered["nombre"].str.contains(filtro2, case=False, na=False)]
    
        df_si_display = rename_columns_for_display(df_si_filtered)
    
        # Recuperar id si fue removida por el rename
        if df_si_display is None:
            df_si_display = pd.DataFrame()
    
        if "id" not in df_si_display.columns and "id" in df_si_filtered.columns:
            try:
                df_si_display["id"] = df_si_filtered["id"].astype(int)
            except Exception:
                df_si_display["id"] = df_si_filtered["id"].astype(str)
    
        if df_si_display.empty:
            st.info("No hay clientes contactados para mostrar.")
        else:
            orig_si_key = "orig_si_map"
            orig_si_map = {str(r.get("id")): r for r in df_si_display.to_dict("records")}
            st.session_state[orig_si_key] = orig_si_map
    
            gb2 = GridOptionsBuilder.from_dataframe(df_si_display)
            gb2.configure_default_column(filterable=True, sortable=True, resizable=True)
    
            if "id" in df_si_display.columns:
                gb2.configure_column("id", hide=True, editable=False)
    
            gb2.configure_selection(selection_mode="multiple", use_checkbox=True)
            visible_cols = [c for c in df_si_display.columns if c != "id"]
            first_col = visible_cols[0] if visible_cols else "id"
            try:
                gb2.configure_column(first_col, checkboxSelection=True, headerCheckboxSelection=True)
            except Exception:
                pass
    
            gb2.configure_column("Nombre", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("NIT", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Persona de Contacto", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Dirección", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Ciudad", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Teléfono", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Email", editable=True, cellEditor="agTextCellEditor")
            gb2.configure_column("Observación", editable=True, cellEditor="agLargeTextCellEditor")
            gb2.configure_column("Última Fecha de Contacto", editable=True, cellEditor="agDateCellEditor")
            gb2.configure_column("Contactado", editable=True, cellEditor="agCheckboxCellEditor")
    
            gridOptions2 = gb2.build()
    
            grid_response2 = AgGrid(
                df_si_display,
                gridOptions=gridOptions2,
                enable_enterprise_modules=False,
                update_mode=GridUpdateMode.MODEL_CHANGED,
                data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
                fit_columns_on_grid_load=True,
                height=420
            )
    
            # --- Guardado automático de ediciones ---
            try:
                edited2 = pd.DataFrame(grid_response2.get("data", []))
                if not edited2.empty:
                    orig_map2 = st.session_state.get(orig_si_key, {})
                    applied_any_update = False
    
                    for _, row in edited2.iterrows():
                        rid_raw = row.get("id")
                        if rid_raw is None:
                            continue
                        try:
                            rid_str = str(int(rid_raw))
                        except Exception:
                            rid_str = str(rid_raw)
    
                        orig_row = orig_map2.get(rid_str, {})
                        updates_db = {}
    
                        for disp_col in edited2.columns:
                            if disp_col == "id":
                                continue
                            old_val = orig_row.get(disp_col)
                            new_val = row.get(disp_col)
                            if (pd.isna(old_val) and (new_val is not None and new_val != "")) or (not pd.isna(old_val) and old_val != new_val):
                                db_col = display_to_db.get(disp_col)
                                if not db_col:
                                    continue
    
                                if db_col == "fecha_contacto":
                                    try:
                                        if new_val in (None, "", "None", "null", "NULL"):
                                            updates_db[db_col] = None
                                        elif isinstance(new_val, str) and new_val.strip() in ("{}", "{ }"):
                                            updates_db[db_col] = None
                                        elif isinstance(new_val, dict):
                                            date_candidate = new_val.get("date") or new_val.get("value") or next(iter(new_val.values()), None)
                                            parsed = pd.to_datetime(date_candidate, errors="coerce")
                                            updates_db[db_col] = None if pd.isna(parsed) else str(parsed.date())
                                        elif hasattr(new_val, "date"):
                                            try:
                                                updates_db[db_col] = str(new_val.date())
                                            except Exception:
                                                updates_db[db_col] = None
                                        else:
                                            parsed = pd.to_datetime(new_val, errors="coerce")
                                            updates_db[db_col] = None if pd.isna(parsed) else str(parsed.date())
                                    except Exception:
                                        updates_db[db_col] = None
    
                                elif db_col == "contactado":
                                    if isinstance(new_val, bool):
                                        updates_db[db_col] = new_val
                                    else:
                                        updates_db[db_col] = bool(new_val)
                                else:
                                    updates_db[db_col] = new_val
    
                        if updates_db:
                            try:
                                try:
                                    cliente_id_param = int(rid_str)
                                except Exception:
                                    cliente_id_param = rid_str
                                actualizar_cliente_campos(cliente_id_param, updates_db)
                                applied_any_update = True
                                orig_map2.setdefault(rid_str, {})
                                for k_disp, v in row.items():
                                    orig_map2[rid_str][k_disp] = v
                            except Exception as e:
                                st.error(f"Error guardando cambios para id {rid_str}: {e}")
    
                    # persistimos el mapa actualizado
                    st.session_state[orig_si_key] = orig_map2
                    
                    # --------- REFRESCAR INMEDIATAMENTE LOS DF desde la BD (TAB 2) ----------
                    try:
                        if is_admin:
                            if filtrar_base and filtrar_base != "Todas":
                                df_no = obtener_clientes(contactado=False, username=None, is_admin=True, base_name=filtrar_base)
                                df_si = obtener_clientes(contactado=True, username=None, is_admin=True, base_name=filtrar_base)
                            elif filtrar_username:
                                df_no = obtener_clientes(contactado=False, username=filtrar_username, is_admin=True)
                                df_si = obtener_clientes(contactado=True, username=filtrar_username, is_admin=True)
                            else:
                                df_no = obtener_clientes(contactado=False, is_admin=True)
                                df_si = obtener_clientes(contactado=True, is_admin=True)
                        else:
                            selected_base = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
                            if selected_base == "TRANSLOGISTIC":
                                df_no = obtener_clientes(contactado=False, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                                df_si = obtener_clientes(contactado=True, username=None, is_admin=False, base_name="TRANSLOGISTIC")
                            else:
                                internal_base = f"{username}__{selected_base}"
                                df_no = obtener_clientes(contactado=False, username=username, is_admin=False, base_name=internal_base)
                                df_si = obtener_clientes(contactado=True, username=username, is_admin=False, base_name=internal_base)
                    
                        st.session_state['df_no_cached'] = df_no
                        st.session_state['df_si_cached'] = df_si
                    
                        st.info(f"✅ Datos recargados: No contactados={len(df_no) if df_no is not None else 0}, Contactados={len(df_si) if df_si is not None else 0}")
                    except Exception as e:
                        st.error(f"Error refrescando datos desde BD: {e}")
                    
                    if applied_any_update:
                        safe_rerun()

    
            except Exception as e:
                st.text(f"(Aviso) Error procesando ediciones automáticas en Contactados: {e}")
    
            # Exportar Contactados, eliminar, etc.

    
            # Exportar Contactados
            st.download_button(
                "⬇️ Exportar Contactados a Excel",
                data=exportar_excel(df_si_filtered),
                file_name="clientes_contactados.xlsx"
            )
    
            # Acciones sobre filas seleccionadas (ej: eliminar)
            selected = grid_response2.get("selected_rows", [])
            # Comprobación explícita para evitar ValueError si viene un DataFrame
            if selected is not None and len(selected) > 0:
                st.markdown(f"**Filas seleccionadas:** {len(selected)}")
                if st.button("🗑️ Eliminar seleccionados (Contactados)", key="eliminar_si"):
                    st.warning("Confirmar: se eliminarán los clientes seleccionados.")
                    if st.button("Confirmar eliminación seleccionados (Contactados)", key="confirm_eliminar_si"):
                        try:
                            deleted_any = False
                            for row in selected:
                                if hasattr(row, "to_dict"):
                                    row = row.to_dict()
                                rid = row.get("id")
                                if not rid:
                                    continue
                                try:
                                    eliminar_cliente(int(rid))
                                    deleted_any = True
                                except Exception as e:
                                    st.error(f"No se pudo eliminar id {rid}: {e}")
                            if deleted_any:
                                st.success("Clientes seleccionados eliminados ✅")
                                # Forzar refresh para que la vista se actualice inmediatamente
                                safe_rerun()
                            else:
                                st.info("No se eliminaron registros.")
                        except Exception as e:
                            st.error(f"No se pudieron eliminar: {e}")

    # --------------------------
    # Vista detallada y edición
    # --------------------------
    st.markdown("---")
    st.subheader("🔎 Vista Detallada por Cliente")

    # Obtener clientes para selector (para admin respetar filtros)
    if is_admin:
        # Si el admin puso un filtro de base en la sidebar (filtrar_base), aplica
        if 'filtrar_base' in locals() and filtrar_base and filtrar_base != "Todas":
            clientes = obtener_clientes(is_admin=True, base_name=filtrar_base)
        else:
            clientes = obtener_clientes(is_admin=True)
    else:
        selected = st.session_state.get("selected_base_view", "TRANSLOGISTIC")
        if selected == "TRANSLOGISTIC":
            clientes = obtener_clientes(contactado=None, username=None, is_admin=False, base_name="TRANSLOGISTIC")
        else:
            # selected es un display name; convertir a internal
            internal_base = f"{username}__{selected}"
            clientes = obtener_clientes(username=username, is_admin=False, base_name=internal_base)

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
        
            # Botón para guardar cambios (este SÍ está dentro del form)
            if st.form_submit_button("💾 Guardar cambios"):
                try:
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
                except Exception as e:
                    st.error(f"Error guardando cambios: {e}")
        
        # ---- Fuera del form: acciones críticas (eliminar) ----
        # Mantener botones fuera del 'with st.form' para evitar StreamlitAPIException
        col_left, col_right = st.columns([1,1])
        with col_right:
            # Paso 1: mostrar botón inicial de eliminación (fuera del form)
            if st.button("🗑️ Eliminar cliente"):
                # Guardamos la intención de eliminar en session_state para mostrar confirmación
                st.session_state.setdefault("confirm_delete_cliente", cliente["id"])
        
        # Si existe intención registrada y coincide con el cliente actual, mostramos confirmación
        if st.session_state.get("confirm_delete_cliente") == cliente["id"]:
            st.warning("⚠️ Estás a punto de eliminar este cliente. Esta acción es irreversible.")
            confirma = st.button("Confirmar eliminación")
            cancelar = st.button("Cancelar eliminación")
            if confirma:
                try:
                    eliminar_cliente(int(cliente["id"]))
                    st.success("Cliente eliminado ✅")
                    st.session_state.pop("confirm_delete_cliente", None)
                    # Forzar refresh para que la lista y los tabs se actualicen
                    safe_rerun()
                except Exception as e:
                    st.error(f"No se pudo eliminar el cliente: {e}")

            if cancelar:
                st.session_state.pop("confirm_delete_cliente", None)
                st.info("Eliminación cancelada.")
        

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

    st.markdown("---")
    st.markdown("<div style='text-align:center; padding: 12px;'>"
                "<h3 style='margin-bottom:6px;color:white;'>Sigue al Creador - SECRET C</h3>"
                f"<a href='https://open.spotify.com/artist/2BrdB1i0wFfQFppxPvYFTy' target='_blank' title='Spotify'>"
                "<img src='https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/spotify.svg' style='height:34px;margin:0 10px;vertical-align:middle;'/>"
                "</a>"
                f"<a href='https://www.instagram.com/imsecretc/' target='_blank' title='Instagram'>"
                "<img src='https://cdn.jsdelivr.net/gh/simple-icons/simple-icons/icons/instagram.svg' style='height:34px;margin:0 10px;vertical-align:middle;'/>"
                "</a>"
                "</div>", unsafe_allow_html=True)

elif st.session_state.get("authentication_status") is False:
    st.sidebar.error("❌ Usuario o contraseña incorrectos")

else:  # authentication_status es None
    st.sidebar.warning("🔑 Por favor ingresa tus credenciales")
