import streamlit as st
import psycopg2
import pandas as pd
from datetime import date


# Configuración de página
st.set_page_config(
    page_title="Sistema de Stock con Movimientos",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)


# Obtener de variables de entorno o secrets de Streamlit
DATABASE_URL = st.secrets.get("DATABASE_URL")




# Estilos CSS (mismos que antes)
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
        color: #212529; /* 🔹 texto oscuro */
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
    """Probar la conexión a la base de datos"""
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
        # Opción 1: Connection string directa
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
    """Forzar reconexión limpiando el cache"""
    init_connection.clear()
    load_stock_data.clear()
    load_obras_data.clear()
    load_movimientos_data.clear()
    st.success("🔄 Cache de conexión limpiado. Intentando reconectar...")

def render_connection_status():
    """Renderizar estado de conexión y botón de reconexión"""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        is_connected, message = test_connection()
        if is_connected:
            st.markdown(f'<div class="db-status db-connected">🟢 {message}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="db-status db-disconnected">🔴 {message}</div>', unsafe_allow_html=True)
    
    with col2:
        if st.button("🔄 Reconectar DB"):
            force_reconnect()
            st.rerun()
    
    with col3:
        if st.button("🧪 Test Conexión"):
            is_connected, message = test_connection()
            if is_connected:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")

def execute_query(query, params=None, fetch=True):
    """Ejecutar consultas de forma segura"""
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

@st.cache_data(ttl=30)  # Cache por 30 segundos
def load_stock_data():
    """Cargar datos de stock"""
    try:
        query = "SELECT * FROM stock ORDER BY id DESC"
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando stock: {str(e)}")
        return []

@st.cache_data(ttl=30)
def load_obras_data():
    """Cargar datos de obras"""
    try:
        query = "SELECT * FROM obras ORDER BY nombre"
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando obras: {str(e)}")
        return []

@st.cache_data(ttl=30)
def load_movimientos_data():
    """Cargar datos de movimientos"""
    try:
        query = """
        SELECT m.*, s.nombre as item_nombre 
        FROM movimientos m 
        LEFT JOIN stock s ON m.item_id = s.id 
        ORDER BY m.fecha_movimiento DESC
        """
        return execute_query(query)
    except Exception as e:
        st.error(f"Error cargando movimientos: {str(e)}")
        return []

def add_item(nombre, tipo, estado='Disponible', obra_actual=None, observaciones=None):
    """Agregar nuevo item"""
    try:
        query = """
        INSERT INTO stock (nombre, tipo, estado, obra_actual, observaciones)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """
        execute_query(query, (nombre, tipo, estado, obra_actual, observaciones))
        load_stock_data.clear()  # ✅ limpiar solo cache de stock
        return True
    except Exception as e:
        st.error(f"Error agregando item: {str(e)}")
        return False
    
def update_item_state(item_id, new_state):
    """Actualizar el estado de un item en stock"""
    try:
        if new_state == "Disponible":
            query = "UPDATE stock SET estado=%s, obra_actual=NULL WHERE id=%s"
            execute_query(query, (new_state, item_id), fetch=False)
        else:
            query = "UPDATE stock SET estado=%s WHERE id=%s"
            execute_query(query, (new_state, item_id), fetch=False)
        load_stock_data.clear()
        st.success("✅ Estado actualizado")
    except Exception as e:
        st.error(f"Error actualizando estado: {str(e)}")


def register_movement(item_id, obra_origen, obra_destino, responsable, motivo, observaciones=None):
    """Registrar movimiento"""
    conn = init_connection()
    if conn is None:
        st.error("❌ No se pudo establecer conexión con la base de datos")
        return False
        
    cur = conn.cursor()
    try:
        # Insertar movimiento
        cur.execute("""
        INSERT INTO movimientos (item_id, obra_origen, obra_destino, responsable, motivo, observaciones)
        VALUES (%s, %s, %s, %s, %s, %s)
        """, (item_id, obra_origen, obra_destino, responsable, motivo, observaciones))
        
        # Actualizar ubicación del item
        cur.execute("""
        UPDATE stock 
        SET obra_actual = %s, estado = 'En uso'
        WHERE id = %s
        """, (obra_destino, item_id))
        
        conn.commit()
        load_movimientos_data.clear()  # ✅ limpiar solo cache de movimientos
        load_stock_data.clear()        # ✅ también stock, porque se actualiza
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Error registrando movimiento: {str(e)}")
        return False
    finally:
        cur.close()


def add_obra(nombre, direccion=None, responsable=None, fecha_inicio=None, fecha_fin=None, estado='Activa'):
    """Agregar nueva obra"""
    try:
        query = """
        INSERT INTO obras (nombre, direccion, responsable, fecha_inicio, fecha_fin, estado)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (nombre) DO NOTHING
        RETURNING id
        """
        execute_query(query, (nombre, direccion, responsable, fecha_inicio, fecha_fin, estado), fetch=False)
        load_obras_data.clear()  # ✅ limpiar solo cache de obras
        return True
    except Exception as e:
        st.error(f"Error agregando obra: {str(e)}")
        return False

def render_dashboard():
    """Dashboard principal"""
    st.markdown('<div class="main-header"><h1>📦 Sistema de Gestión de Stock y Movimientos</h1></div>', unsafe_allow_html=True)
    
    # Cargar datos
    df_stock = pd.DataFrame(load_stock_data())
    df_movimientos = pd.DataFrame(load_movimientos_data())
    
    # Métricas principales
    if not df_stock.empty:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("📦 Total Items", len(df_stock))
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

    # Movimientos recientes
    st.subheader("🚚 Movimientos Recientes")
    if not df_movimientos.empty:
        recent = df_movimientos.head(5)
        for _, mov in recent.iterrows():
            fecha = pd.to_datetime(mov["fecha_movimiento"]).strftime("%d/%m/%Y %H:%M")
            with st.container():
                st.markdown(
                    f"""
                    <div class="movement-card">
                        <strong>{mov.get('item_nombre','Item desconocido')}</strong><br>
                        🚛 {mov.get('obra_origen','Sin origen')} → {mov.get('obra_destino','Sin destino')}<br>
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
        st.info("No hay items en el inventario")
        return

    # Buscador que filtra todas las columnas
    search = st.text_input("🔎 Buscar item (nombre, tipo, estado, obra, observaciones)")

    if search:
        mask = df_stock.apply(lambda row: row.astype(str).str.contains(search, case=False, na=False).any(), axis=1)
        df_filtered = df_stock[mask]
    else:
        df_filtered = df_stock

    if df_filtered.empty:
        st.info("No se encontraron coincidencias")
        return

    # Checkbox para activar Modo Edición
    edit_mode = st.checkbox("🖊️ Modo Edición")

    if edit_mode:
        # Mostrar lista con opción de editar estado
        for _, row in df_filtered.iterrows():
            col1, col2, col3 = st.columns([5,3,2])
            with col1:
                st.markdown(f"**{row['nombre']}** | {row['tipo']} | Estado: {row['estado']} | Obra: {row.get('obra_actual','Sin obra')}")
            with col2:
                estados = ["Disponible", "En uso", "Mantenimiento"]
                index = estados.index(row['estado']) if row['estado'] in estados else 0
                new_state = st.selectbox("Cambiar estado", estados, index=index, key=f"state_{row['id']}")
            with col3:
                if st.button("Actualizar", key=f"update_{row['id']}"):
                    update_item_state(row['id'], new_state)
    else:
        # Modo solo lectura: mostrar tabla completa
        st.dataframe(df_filtered, use_container_width=True)


def render_add_item():
    """Formulario para agregar items"""
    st.subheader("➕ Agregar Nuevo Item")
    
    with st.form("add_item"):
        col1, col2 = st.columns(2)
        
        with col1:
            nombre = st.text_input("* Nombre", placeholder="Ej: Taladro Bosch")
            tipo = st.selectbox("* Tipo", ["Herramienta", "Maquina", "Material", "Equipo"])
            estado = st.selectbox("Estado", ["Disponible", "En uso", "Mantenimiento"])
        
        with col2:
            obra_actual = st.text_input("Obra Actual", placeholder="Ej: Edificio Central")
            observaciones = st.text_area("Observaciones")
        
        submitted = st.form_submit_button("💾 Guardar Item")
        
        if submitted:
            if not nombre:
                st.error("❌ El nombre es obligatorio")
            else:
                if add_item(nombre, tipo, estado, obra_actual, observaciones):
                    st.success(f"✅ Item '{nombre}' agregado exitosamente!")
                    # Limpiar inputs
                    st.session_state.pop("add_item_nombre", None)
                    st.session_state.pop("add_item_obra_actual", None)
                    st.session_state.pop("add_item_observaciones", None)


def render_register_movement():
    st.subheader("🚚 Registrar Movimiento")
    
    df_stock = pd.DataFrame(load_stock_data())
    df_obras = pd.DataFrame(load_obras_data())
    
    if df_stock.empty:
        st.warning("No hay items disponibles para mover")
        return
    
    # Buscador tipo selectbox
    search_options = df_stock.apply(
    lambda r: f"{r['nombre']} | {r['tipo']} | Estado: {r['estado']} | Obra: {r.get('obra_actual','Sin obra')} | ID:{r['id']}", axis=1
).tolist()
    
    selected_str = st.selectbox("🔎 Seleccionar item para mover", [""] + search_options)
    
    if selected_str:
        selected_item_id = int(selected_str.split("ID:")[-1])
        item = df_stock[df_stock['id'] == selected_item_id].iloc[0]
        current_obra = item['obra_actual']
        st.info(f"Item seleccionado: {item['nombre']} | {item['tipo']} | Obra actual: {current_obra or 'Sin obra'}")
        
        with st.form("register_movement_form"):
            # Obras destino
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
                    obra_final = nueva_obra.strip() if nueva_obra.strip() else obra_destino
                    if not obra_final or obra_final == "(Sin obras registradas)":
                        st.error("❌ Debe especificar una obra destino")
                    else:
                        if nueva_obra.strip():
                            add_obra(nueva_obra.strip())
                        motivo_final = motivo_custom if motivo == "Otros" and motivo_custom else motivo
                        if register_movement(selected_item_id, current_obra, obra_final, responsable, motivo_final, observaciones):
                            st.success("✅ Movimiento registrado exitosamente!")
                            st.session_state["selected_item_id"] = None
                            st.rerun()

def render_reports():
    """Página de reportes"""
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
                st.write("**Items más movidos**")
                most_moved = df_movimientos['item_nombre'].value_counts().head(10)
                st.bar_chart(most_moved)
        
        with tab2:
            st.write("**Historial completo de movimientos**")
            st.dataframe(
                df_movimientos[['fecha_movimiento','item_nombre','obra_origen','obra_destino','responsable','motivo']], 
                use_container_width=True
            )
        
        with tab3:
            st.write("**Filtros avanzados**")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                responsable_filter = st.selectbox("Filtrar por responsable", ["Todos"] + df_movimientos['responsable'].unique().tolist())
            with col2:
                item_filter = st.selectbox("Filtrar por item", ["Todos"] + df_movimientos['item_nombre'].dropna().unique().tolist())
            with col3:
                fecha_desde = st.date_input("Desde fecha")
            
            # Aplicar filtros
            df_filtered = df_movimientos.copy()
            
            if responsable_filter != "Todos":
                df_filtered = df_filtered[df_filtered['responsable'] == responsable_filter]
            
            if item_filter != "Todos":
                df_filtered = df_filtered[df_filtered['item_nombre'] == item_filter]
            
            df_filtered = df_filtered[pd.to_datetime(df_filtered['fecha_movimiento']).dt.date >= fecha_desde]
            
            st.write(f"**Resultados filtrados ({len(df_filtered)} registros)**")
            if not df_filtered.empty:
                st.dataframe(
                    df_filtered[['fecha_movimiento','item_nombre','obra_origen','obra_destino','responsable','motivo']], 
                    use_container_width=True
                )
            else:
                st.info("No se encontraron registros con los filtros aplicados")
    else:
        st.info("No hay movimientos registrados para generar reportes")

def main():
    st.sidebar.title("🧭 Navegación")
    
    # Estado de conexión en sidebar - más compacto
    st.sidebar.markdown("**🔌 Base de Datos**")
    
    is_connected, message = test_connection()
    if is_connected:
        st.sidebar.markdown("🟢 **Conectado**")
    else:
        st.sidebar.markdown("🔴 **Desconectado**")
    
    # Botones de conexión en una fila
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.sidebar.button("🔄 Reconectar"):
            force_reconnect()
            st.rerun()
    with col2:
        if st.sidebar.button("🧪 Test"):
            is_connected, message = test_connection()
            if is_connected:
                st.sidebar.success("✅ OK")
            else:
                st.sidebar.error("❌ Error")
    
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