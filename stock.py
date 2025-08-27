
import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

# Configuración de página
st.set_page_config(
    page_title="Sistema de Herramientas con Movimientos",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Obtener de variables de entorno o secrets de Streamlit
DATABASE_URL = st.secrets.get("DATABASE_URL")

# Estilos CSS
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(90deg, #1f77b4, #2ca02c);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
    }
    .movement-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #28a745;
        margin: 0.5rem 0;
        color: #212529;
        font-size: 0.95rem;
        line-height: 1.4;
    }
    .movement-card strong {
        font-size: 1.05rem;
        color: #000;
    }
    .db-status {
        padding: 0.5rem 1rem;
        border-radius: 5px;
        margin-bottom: 1rem;
        font-weight: bold;
    }
    .db-connected {
        background-color: #d4edda;
        color: #155724;
        border: 1px solid #c3e6cb;
    }
    .db-disconnected {
        background-color: #f8d7da;
        color: #721c24;
        border: 1px solid #f5c6cb;
    }
</style>
""", unsafe_allow_html=True)

def test_connection():
    try:
        database_url = st.secrets["DATABASE_URL"]
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        cursor.fetchone()
        cursor.close()
        conn.close()
        return True, "Conexión exitosa"
    except KeyError:
        return False, "Falta DATABASE_URL en secrets"
    except psycopg2.OperationalError as e:
        return False, f"Error de conexión: {str(e)}"
    except Exception as e:
        return False, f"Error inesperado: {str(e)}"

@st.cache_resource
def init_connection():
    try:
        database_url = st.secrets["DATABASE_URL"]
        conn = psycopg2.connect(database_url)
        return conn
    except KeyError:
        st.error("❌ Falta DATABASE_URL en secrets")
        return None
    except Exception as e:
        st.error(f"❌ Error de conexión: {e}")
        return None

def force_reconnect():
    init_connection.clear()
    load_stock_data.clear()
    load_obras_data.clear()
    load_movimientos_data.clear()
    st.success("🔄 Cache de conexión limpiado. Intentando reconectar...")

def execute_query(query, params=None, fetch=True):
    conn = init_connection()
    if conn is None:
        raise Exception("No se pudo establecer conexión con la base de datos")
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        if fetch:
            if query.strip().upper().startswith('SELECT'):
                columns = [desc[0] for desc in cur.description]
                data = cur.fetchall()
                return [dict(zip(columns, row)) for row in data]
            else:
                conn.commit()
                return True
        else:
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

# -------------------- Helpers de Obras --------------------
def get_or_create_obra_id(nombre: str):
    if not nombre or not nombre.strip():
        return None
    conn = init_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM obras WHERE nombre = %s", (nombre.strip(),))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute("INSERT INTO obras (nombre, estado) VALUES (%s, 'Activa') RETURNING id", (nombre.strip(),))
        new_id = cur.fetchone()[0]
        conn.commit()
        return new_id
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

@st.cache_data(ttl=30)
def load_stock_data():
    # Compatible con obra_actual VARCHAR o INTEGER
    try:
        query = """
        SELECT h.*,
               COALESCE(o_id.nombre, o_nm.nombre) AS obra_actual_nombre
        FROM herramientas h
        LEFT JOIN obras o_id
               ON o_id.id = CASE WHEN h.obra_actual ~ '^[0-9]+$' THEN (h.obra_actual)::int ELSE NULL END
        LEFT JOIN obras o_nm
               ON o_nm.nombre = h.obra_actual
        ORDER BY h.id DESC
        """
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando herramientas: {str(e)}")
        return []

@st.cache_data(ttl=30)
def load_obras_data():
    try:
        query = "SELECT * FROM obras ORDER BY nombre"
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando obras: {str(e)}")
        return []

@st.cache_data(ttl=30)
def load_movimientos_data():
    try:
        query = """
        SELECT m.*,
               h.nombre AS item_nombre,
               h.marca  AS item_marca,
               COALESCE(o1_id.nombre, o1_nm.nombre) AS obra_origen_nombre,
               COALESCE(o2_id.nombre, o2_nm.nombre) AS obra_destino_nombre
        FROM movimientos m
        LEFT JOIN herramientas h ON m.item_id = h.id
        LEFT JOIN obras o1_id
               ON o1_id.id = CASE WHEN m.obra_origen ~ '^[0-9]+$' THEN (m.obra_origen)::int ELSE NULL END
        LEFT JOIN obras o1_nm
               ON o1_nm.nombre = m.obra_origen
        LEFT JOIN obras o2_id
               ON o2_id.id = CASE WHEN m.obra_destino ~ '^[0-9]+$' THEN (m.obra_destino)::int ELSE NULL END
        LEFT JOIN obras o2_nm
               ON o2_nm.nombre = m.obra_destino
        ORDER BY m.fecha_movimiento DESC
        """
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando movimientos: {str(e)}")
        return []

def add_item(nombre, tipo, estado='Disponible', obra_actual=None, observaciones=None, marca=None):
    # Marca por defecto para mantener compatibilidad si no la completan
    try:
        obra_id = None
        if obra_actual and obra_actual.strip():
            obra_id = get_or_create_obra_id(obra_actual.strip())

        marca_val = (marca or '').strip() or 'N/D'

        query = """
        INSERT INTO herramientas (marca, nombre, tipo, estado, obra_actual, observaciones)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        conn = init_connection()
        cur = conn.cursor()
        cur.execute(query, (marca_val, nombre, tipo, estado, obra_id, observaciones))
        conn.commit()
        cur.close()

        load_stock_data.clear()
        return True
    except Exception as e:
        st.error(f"Error agregando herramienta: {str(e)}")
        return False
    
def add_obra(nombre, estado='Activa'):
    """Agrega una nueva obra si no existe."""
    try:
        conn = init_connection()
        cur = conn.cursor()
        # Verifica si ya existe
        cur.execute("SELECT id FROM obras WHERE nombre = %s", (nombre.strip(),))
        if cur.fetchone():
            cur.close()
            return False  # Ya existe
        # Inserta nueva obra
        cur.execute(
            "INSERT INTO obras (nombre, estado) VALUES (%s, %s)",
            (nombre.strip(), estado)
        )
        conn.commit()
        cur.close()
        load_obras_data.clear()
        return True
    except Exception as e:
        st.error(f"Error agregando obra: {str(e)}")
        return False

def update_item_state(item_id, new_state):
    try:
        if new_state == "Disponible":
            query = "UPDATE herramientas SET estado=%s, obra_actual=NULL WHERE id=%s"
            execute_query(query, (new_state, item_id), fetch=False)
        else:
            query = "UPDATE herramientas SET estado=%s WHERE id=%s"
            execute_query(query, (new_state, item_id), fetch=False)
        load_stock_data.clear()
        st.success("✅ Estado actualizado")
    except Exception as e:
        st.error(f"Error actualizando estado: {str(e)}")

def register_movement(item_id, obra_origen_nombre, obra_destino_nombre, responsable, motivo, observaciones=None):
    conn = init_connection()
    if conn is None:
        st.error("❌ No se pudo establecer conexión con la base de datos")
        return False

    cur = conn.cursor()
    try:
        obra_origen_id = get_or_create_obra_id(obra_origen_nombre) if obra_origen_nombre else None
        obra_destino_id = get_or_create_obra_id(obra_destino_nombre) if obra_destino_nombre else None

        cur.execute("""
            INSERT INTO movimientos (item_id, obra_origen, obra_destino, responsable, motivo, observaciones)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (item_id, obra_origen_id, obra_destino_id, responsable, motivo, observaciones))

        cur.execute("""
            UPDATE herramientas
            SET obra_actual = %s, estado = 'En uso'
            WHERE id = %s
        """, (obra_destino_id, item_id))

        conn.commit()
        load_movimientos_data.clear()
        load_stock_data.clear()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error registrando movimiento: {str(e)}")
        return False
    finally:
        cur.close()

def render_dashboard():
    st.markdown('<div class="main-header"><h1>📦 Sistema de Herramientas y Movimientos</h1></div>', unsafe_allow_html=True)

    df_stock = pd.DataFrame(load_stock_data())
    df_movimientos = pd.DataFrame(load_movimientos_data())

    if not df_stock.empty:
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("🧰 Total Herramientas", len(df_stock))
        with col2:
            disponibles = len(df_stock[df_stock['estado'] == 'Disponible'])
            st.metric("✅ Disponibles", disponibles)
        with col3:
            en_uso = len(df_stock[df_stock['estado'] == 'En uso'])
            st.metric("🔧 En Uso", en_uso)
        with col4:
            mantenimiento = len(df_stock[df_stock['estado'] == 'Mantenimiento'])
            st.metric("⚠️ Mantenimiento", mantenimiento)
        with col5:
            if not df_movimientos.empty:
                today_movements = len(df_movimientos[pd.to_datetime(df_movimientos['fecha_movimiento']).dt.date == date.today()])
            else:
                today_movements = 0
            st.metric("🚚 Movimientos Hoy", today_movements)

    st.subheader("🚚 Movimientos Recientes")
    if not df_movimientos.empty:
        recent = df_movimientos.head(5)
        for _, mov in recent.iterrows():
            fecha = pd.to_datetime(mov["fecha_movimiento"]).strftime("%d/%m/%Y %H:%M")
            display_name = (mov.get('item_marca') or '') + (' ' if mov.get('item_marca') else '') + (mov.get('item_nombre') or 'Item')
            origen = mov.get('obra_origen_nombre','Sin origen')
            destino = mov.get('obra_destino_nombre','Sin destino')
            st.markdown(f"""
                <div class="movement-card">
                    <strong>{display_name}</strong><br>
                    🚛 {origen} → {destino}<br>
                    📅 {fecha} &nbsp; | &nbsp; 👤 {mov.get('responsable','N/A')}<br>
                    📝 {mov.get('motivo','Sin motivo')}
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No hay movimientos registrados")

def render_stock_page():
    st.subheader("📋 Inventario Actual")
    df_stock = pd.DataFrame(load_stock_data())

    if df_stock.empty:
        st.info("No hay herramientas en el inventario")
        return

    # --- FILTROS ---
    col_search, col_obra = st.columns([3,2])
    with col_search:
        search = st.text_input("🔎 Buscar (marca, nombre, tipo, estado)")
    with col_obra:
        obras = sorted(df_stock['obra_actual_nombre'].dropna().unique().tolist())
        obra_selected = st.selectbox("Filtrar por obra", ["Todas"] + obras)

    # --- FILTRADO ---
    df_filtered = df_stock.copy()
    if search:
        mask = df_filtered.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
        df_filtered = df_filtered[mask]
    if obra_selected and obra_selected != "Todas":
        df_filtered = df_filtered[df_filtered['obra_actual_nombre'] == obra_selected]

    
    if df_filtered.empty:
        st.info("No se encontraron coincidencias")
        return
    col_edit, col_refesh = st.columns([5,1])
    with col_edit:
        edit_mode = st.checkbox("🖊️ Modo Edición")
    with col_refesh:
        if st.button("🔄 Actualizar tabla"):
            load_stock_data.clear()
            st.experimental_rerun()

    df_stock = pd.DataFrame(load_stock_data())

    # Armamos una vista amigable: ocultar obra_actual (id/texto) y mostrar solo el nombre
    df_display = df_filtered.copy()
    if 'obra_actual' in df_display.columns:
        df_display = df_display.drop(columns=['obra_actual'])
    if 'obra_actual_nombre' in df_display.columns:
        df_display = df_display.rename(columns={'obra_actual_nombre': 'Obra'})

    # Reordenar columnas (si existen)
    preferred = ['id', 'marca', 'nombre', 'tipo', 'estado', 'Obra', 'observaciones', 'created_at']
    cols = [c for c in preferred if c in df_display.columns] + [c for c in df_display.columns if c not in preferred]

    if edit_mode:
        for _, row in df_filtered.iterrows():
            col1, col2, col3 = st.columns([5,3,2])
            with col1:
                st.markdown(f"**{row.get('marca','')} {row['nombre']}** | {row['tipo']} | Estado: {row['estado']} | Obra: {row.get('obra_actual_nombre','Sin obra')}")
            with col2:
                estados = ["Disponible", "En uso", "Mantenimiento"]
                index = estados.index(row['estado']) if row['estado'] in estados else 0
                new_state = st.selectbox("Cambiar estado", estados, index=index, key=f"state_{row['id']}")
            with col3:
                if st.button("Actualizar", key=f"update_{row['id']}"):
                    update_item_state(row['id'], new_state)
    else:
        st.dataframe(df_display[cols], use_container_width=True, hide_index=True)

def render_add_item():
    st.subheader("➕ Agregar Nueva Herramienta")

    with st.form("add_item"):
        col1, col2 = st.columns(2)
        with col1:
            marca = st.text_input("* Marca", placeholder="Ej: Bosch")
            nombre = st.text_input("* Nombre", placeholder="Ej: Taladro")
            tipo = st.selectbox("* Tipo", ["Electrica", "A explosion", "De mano", "Material", "Equipo"])
        with col2:
            estado = st.selectbox("Estado", ["Disponible", "En uso", "Mantenimiento"])
            obra_actual = st.text_input("Obra Actual", placeholder="Ej: Edificio Central")
            observaciones = st.text_area("Observaciones")
        submitted = st.form_submit_button("💾 Guardar Herramienta")
        if submitted:
            if not nombre or not marca:
                st.error("❌ Marca y Nombre son obligatorios")
            else:
                if add_item(nombre, tipo, estado, obra_actual, observaciones, marca):
                    st.success(f"✅ Herramienta '{marca} {nombre}' agregada exitosamente!")
                    for key in ["add_item_marca","add_item_nombre","add_item_obra_actual","add_item_observaciones"]:
                        st.session_state.pop(key, None)

def render_register_movement():
    st.subheader("🚚 Registrar Movimiento")

    df_stock = pd.DataFrame(load_stock_data())
    df_obras = pd.DataFrame(load_obras_data())

    if df_stock.empty:
        st.warning("No hay herramientas disponibles para mover")
        return

    search_options = df_stock.apply(
        lambda r: f"{r.get('marca','')} {r['nombre']} | {r['tipo']} | Estado: {r['estado']} | Obra: {r.get('obra_actual_nombre','Sin obra')} | ID:{r['id']}",
        axis=1
    ).tolist()

    selected_str = st.selectbox("🔎 Seleccionar herramienta para mover", [""] + search_options)

    if selected_str:
        selected_item_id = int(selected_str.split("ID:")[-1])
        item = df_stock[df_stock['id'] == selected_item_id].iloc[0]
        current_obra_nombre = item.get('obra_actual_nombre')
        st.info(f"Seleccionado: {item.get('marca','')} {item['nombre']} | {item['tipo']} | Obra actual: {current_obra_nombre or 'Sin obra'}")

        with st.form("register_movement_form"):
            obras_list = df_obras['nombre'].tolist()
            obra_destino = st.selectbox("* Obra destino", obras_list if obras_list else ["(Sin obras registradas)"])
            nueva_obra = st.text_input("¿Nueva obra?", placeholder="Nombre de nueva obra")

            responsable = st.text_input("* Responsable")
            motivo = st.selectbox("Motivo", [
                "Traslado por necesidad de obra",
                "Finalización de trabajo",
                "Mantenimiento programado",
                "Reasignación de recursos",
                "Otros"
            ])
            motivo_custom = st.text_input("Motivo personalizado")
            observaciones = st.text_area("Observaciones")

            submitted = st.form_submit_button("🚚 Registrar Movimiento")
            if submitted:
                if not responsable:
                    st.error("❌ El responsable es obligatorio")
                else:
                    obra_final = (nueva_obra or "").strip() or obra_destino
                    if not obra_final or obra_final == "(Sin obras registradas)":
                        st.error("❌ Debe especificar una obra destino")
                    else:
                        if nueva_obra.strip():
                            add_obra(nueva_obra.strip())
                        motivo_final = motivo_custom if motivo == "Otros" and motivo_custom else motivo
                        if register_movement(selected_item_id, current_obra_nombre, obra_final, responsable, motivo_final, observaciones):
                            st.success("✅ Movimiento registrado exitosamente!")
                            st.session_state["selected_item_id"] = None
                            st.rerun()

def render_reports():
    st.subheader("📈 Reportes y Análisis")

    df_movimientos = pd.DataFrame(load_movimientos_data())
    df_stock = pd.DataFrame(load_stock_data())

    if not df_movimientos.empty:
        tab1, tab2, tab3 = st.tabs(["📊 Estadísticas", "📋 Historial Completo", "🔍 Filtros Avanzados"])

        with tab1:
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Movimientos por día (últimos 30)**")
                df_movimientos['fecha'] = pd.to_datetime(df_movimientos['fecha_movimiento']).dt.date
                movements_by_date = df_movimientos['fecha'].value_counts().sort_index().tail(30)
                st.bar_chart(movements_by_date)
            with col2:
                st.write("**Herramientas más movidas**")
                most_moved = df_movimientos['item_nombre'].value_counts().head(10)
                st.bar_chart(most_moved)

        with tab2:
            st.write("**Historial completo de movimientos**")
            st.dataframe(
                df_movimientos[[
                    'fecha_movimiento',
                    'item_marca',
                    'item_nombre',
                    'obra_origen_nombre',
                    'obra_destino_nombre',
                    'responsable',
                    'motivo'
                ]],
                use_container_width=True
            )

        with tab3:
            st.write("**Filtros avanzados**")
            col1, col2, col3 = st.columns(3)
            with col1:
                responsable_filter = st.selectbox("Filtrar por responsable", ["Todos"] + df_movimientos['responsable'].dropna().unique().tolist())
            with col2:
                item_filter = st.selectbox("Filtrar por herramienta", ["Todos"] + df_movimientos['item_nombre'].dropna().unique().tolist())
            with col3:
                fecha_desde = st.date_input("Desde fecha")

            df_filtered = df_movimientos.copy()
            if responsable_filter != "Todos":
                df_filtered = df_filtered[df_filtered['responsable'] == responsable_filter]
            if item_filter != "Todos":
                df_filtered = df_filtered[df_filtered['item_nombre'] == item_filter]
            if fecha_desde:
                df_filtered = df_filtered[pd.to_datetime(df_filtered['fecha_movimiento']).dt.date >= fecha_desde]

            st.write(f"**Resultados filtrados ({len(df_filtered)} registros)**")
            if not df_filtered.empty:
                st.dataframe(
                    df_filtered[[
                        'fecha_movimiento',
                        'item_marca',
                        'item_nombre',
                        'obra_origen_nombre',
                        'obra_destino_nombre',
                        'responsable',
                        'motivo'
                    ]],
                    use_container_width=True
                )
            else:
                st.info("No se encontraron registros con los filtros aplicados")
    else:
        st.info("No hay movimientos registrados para generar reportes")

def main():
    st.sidebar.title("🧭 Navegación")

    st.sidebar.markdown("**🔌 Base de Datos**")
    is_connected, message = test_connection()
    st.sidebar.markdown("🟢 **Conectado**" if is_connected else "🔴 **Desconectado**")
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.sidebar.button("🔄 Reconectar"):
            force_reconnect()
            st.rerun()
    with col2:
        if st.sidebar.button("🧪 Test"):
            is_connected, message = test_connection()
            st.sidebar.success("✅ OK" if is_connected else "❌ Error")

    st.sidebar.markdown("---")
    page = st.sidebar.radio(
        "Ir a:",
        ["📊 Dashboard", "➕ Agregar Item", "🚚 Registrar Movimiento", "📋 Ver Stock", "📈 Reportes"]
    )

    if page == "📊 Dashboard":
        render_dashboard()
    elif page == "➕ Agregar Item":
        render_add_item()
    elif page == "🚚 Registrar Movimiento":
        render_register_movement()
    elif page == "📋 Ver Stock":
        render_stock_page()
    elif page == "📈 Reportes":
        render_reports()

if __name__ == "__main__":
    main()
