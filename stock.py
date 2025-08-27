
import streamlit as st
import psycopg2
import pandas as pd
from datetime import date

# ---------------------- Config ----------------------
st.set_page_config(page_title="Sistema de Herramientas con Movimientos", page_icon="📦", layout="wide")

# ---------------------- Styles ----------------------
st.markdown("""
<style>
    .main-header {background: linear-gradient(90deg, #1f77b4, #2ca02c); padding: 1rem; border-radius: 10px; color: white; text-align: center; margin-bottom: 2rem;}
    .movement-card {background: #f8f9fa; padding: 1rem; border-radius: 8px; border-left: 4px solid #28a745; margin: 0.5rem 0; color: #212529; font-size: 0.95rem; line-height: 1.4;}
    .movement-card strong {font-size: 1.05rem; color: #000;}
</style>
""", unsafe_allow_html=True)

# ---------------------- DB Helpers ----------------------
def _conn():
    try:
        return psycopg2.connect(st.secrets["DATABASE_URL"])
    except KeyError:
        st.error("❌ Falta DATABASE_URL en secrets")
        return None

@st.cache_resource
def init_connection():
    return _conn()

def execute_query(query, params=None, fetch=True):
    conn = init_connection()
    if conn is None:
        raise Exception("No se pudo establecer conexión con la base de datos")
    cur = conn.cursor()
    try:
        cur.execute(query, params or ())
        if fetch and query.strip().upper().startswith("SELECT"):
            cols = [d[0] for d in cur.description]
            data = cur.fetchall()
            return [dict(zip(cols, r)) for r in data]
        else:
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()

def get_or_create_obra_id(nombre: str):
    if not nombre or not nombre.strip() or nombre == "(Sin obra)":
        return None
    conn = init_connection(); cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM obras WHERE nombre = %s", (nombre.strip(),))
        row = cur.fetchone()
        if row: return row[0]
        cur.execute("INSERT INTO obras (nombre, estado) VALUES (%s, 'Activa') RETURNING id", (nombre.strip(),))
        new_id = cur.fetchone()[0]; conn.commit(); return new_id
    except Exception:
        conn.rollback(); raise
    finally:
        cur.close()

# ---------------------- Loaders ----------------------
@st.cache_data(ttl=30)
def load_stock_data():
    q = """
    SELECT h.*,
           COALESCE(o_id.nombre, o_nm.nombre) AS obra_actual_nombre
    FROM herramientas h
    LEFT JOIN obras o_id
           ON o_id.id = CASE WHEN h.obra_actual ~ '^[0-9]+$' THEN (h.obra_actual)::int ELSE NULL END
    LEFT JOIN obras o_nm
           ON o_nm.nombre = h.obra_actual
    ORDER BY h.id DESC
    """
    try:
        return execute_query(q)
    except Exception as e:
        st.error(f"Error cargando herramientas: {e}")
        return []

@st.cache_data(ttl=30)
def load_obras_data():
    try:
        return execute_query("SELECT * FROM obras ORDER BY nombre")
    except Exception as e:
        st.error(f"Error cargando obras: {e}")
        return []

@st.cache_data(ttl=30)
def load_movimientos_data():
    q = """
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
    try:
        return execute_query(q)
    except Exception as e:
        st.error(f"Error cargando movimientos: {e}")
        return []

# ---------------------- Mutations ----------------------
def add_item(nombre, tipo, estado='Disponible', obra_actual=None, observaciones=None, marca=None):
    """Inserta y retorna el ID creado."""
    try:
        obra_id = get_or_create_obra_id((obra_actual or "").strip()) if obra_actual else None
        marca_val = (marca or '').strip() or 'N/D'
        q = """
        INSERT INTO herramientas (marca, nombre, tipo, estado, obra_actual, observaciones)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """
        conn = init_connection(); cur = conn.cursor()
        cur.execute(q, (marca_val, nombre, tipo, estado, obra_id, observaciones))
        new_id = cur.fetchone()[0]; conn.commit(); cur.close()
        load_stock_data.clear()
        return new_id
    except Exception as e:
        st.error(f"Error agregando herramienta: {e}")
        return None

def update_item_state(item_id, new_state):
    try:
        if new_state == "Disponible":
            execute_query("UPDATE herramientas SET estado=%s, obra_actual=NULL WHERE id=%s", (new_state, item_id), fetch=False)
        else:
            execute_query("UPDATE herramientas SET estado=%s WHERE id=%s", (new_state, item_id), fetch=False)
        load_stock_data.clear()
        st.success("✅ Estado actualizado")
    except Exception as e:
        st.error(f"Error actualizando estado: {e}")

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
        conn.commit(); load_movimientos_data.clear(); load_stock_data.clear()
        return True
    except Exception as e:
        conn.rollback(); st.error(f"Error registrando movimiento: {e}"); return False
    finally:
        cur.close()

# ---------------------- UI ----------------------
def render_dashboard():
    st.markdown('<div class="main-header"><h1>📦 Sistema de Herramientas y Movimientos</h1></div>', unsafe_allow_html=True)
    df_stock = pd.DataFrame(load_stock_data()); df_movs = pd.DataFrame(load_movimientos_data())
    if not df_stock.empty:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: st.metric("🧰 Total Herramientas", len(df_stock))
        with c2: st.metric("✅ Disponibles", (df_stock['estado'] == 'Disponible').sum())
        with c3: st.metric("🔧 En Uso", (df_stock['estado'] == 'En uso').sum())
        with c4: st.metric("⚠️ Mantenimiento", (df_stock['estado'] == 'Mantenimiento').sum())
        with c5:
            today = 0 if df_movs.empty else (pd.to_datetime(df_movs['fecha_movimiento']).dt.date == date.today()).sum()
            st.metric("🚚 Movimientos Hoy", today)
    st.subheader("🚚 Movimientos Recientes")
    if not df_movs.empty:
        for _, mov in df_movs.head(5).iterrows():
            fecha = pd.to_datetime(mov["fecha_movimiento"]).strftime("%d/%m/%Y %H:%M")
            display = f"{mov.get('item_marca','')} {mov.get('item_nombre','Item')}".strip()
            st.markdown(f"""
                <div class="movement-card">
                    <strong>{display}</strong><br>
                    🚛 {mov.get('obra_origen_nombre','Sin origen')} → {mov.get('obra_destino_nombre','Sin destino')}<br>
                    📅 {fecha} &nbsp; | &nbsp; 👤 {mov.get('responsable','N/A')}<br>
                    📝 {mov.get('motivo','Sin motivo')}
                </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No hay movimientos registrados")

def render_stock_page():
    st.subheader("📋 Inventario Actual")
    df = pd.DataFrame(load_stock_data())
    if df.empty:
        st.info("No hay herramientas en el inventario"); return
    col_search, col_obra = st.columns([3,2])
    with col_search: search = st.text_input("🔎 Buscar (marca, nombre, tipo, estado)")
    with col_obra:
        obras = sorted(df['obra_actual_nombre'].dropna().unique().tolist())
        obra_sel = st.selectbox("Filtrar por obra", ["Todas"] + obras)
    if search:
        df = df[df.apply(lambda r: r.astype(str).str.contains(search, case=False, na=False).any(), axis=1)]
    if obra_sel != "Todas":
        df = df[df['obra_actual_nombre'] == obra_sel]
    if df.empty:
        st.info("No se encontraron coincidencias"); return
    df_disp = df.copy().drop(columns=[c for c in ['obra_actual'] if c in df.columns])
    if 'obra_actual_nombre' in df_disp.columns: df_disp = df_disp.rename(columns={'obra_actual_nombre':'Obra'})
    pref = ['id','marca','nombre','tipo','estado','Obra','observaciones','created_at']
    cols = [c for c in pref if c in df_disp.columns] + [c for c in df_disp.columns if c not in pref]
    st.dataframe(df_disp[cols], use_container_width=True, hide_index=True)

def render_add_item():
    st.subheader("➕ Agregar Nueva Herramienta")
    df_obras = pd.DataFrame(load_obras_data())
    obras_list = ["(Sin obra)"] + (df_obras['nombre'].tolist() if not df_obras.empty else [])

    with st.form("add_item_form"):
        c1, c2 = st.columns(2)
        with c1:
            marca = st.text_input("* Marca", placeholder="Ej: Bosch")
            nombre = st.text_input("* Nombre", placeholder="Ej: Taladro")
            tipo = st.selectbox("* Tipo", ["Electrica","A explosion","De mano","Material","Equipo"])
        with c2:
            estado = st.selectbox("Estado", ["Disponible","En uso","Mantenimiento", "No funciona"])
            obra_actual = st.selectbox("* Obra actual", obras_list, index=0)
            observaciones = st.text_area("Observaciones")
        submitted = st.form_submit_button("💾 Guardar Herramienta")

    if submitted:
        if not nombre or not marca:
            st.error("❌ Marca y Nombre son obligatorios")
        else:
            new_id = add_item(nombre, tipo, estado, obra_actual, observaciones, marca)
            if new_id:
                st.success(f"✅ Herramienta '{marca} {nombre}' agregada. (ID {new_id})")

def render_register_movement():
    st.subheader("🚚 Registrar Movimiento")
    df_stock = pd.DataFrame(load_stock_data()); df_obras = pd.DataFrame(load_obras_data())
    if df_stock.empty:
        st.warning("No hay herramientas disponibles para mover"); return
    options = df_stock.apply(lambda r: f"{r.get('marca','')} {r['nombre']} | {r['tipo']} | Estado: {r['estado']} | Obra: {r.get('obra_actual_nombre','Sin obra')} | ID:{r['id']}", axis=1).tolist()
    selected = st.selectbox("🔎 Seleccionar herramienta para mover", [""] + options)
    if selected:
        item_id = int(selected.split("ID:")[-1]); item = df_stock[df_stock['id'] == item_id].iloc[0]
        current_obra = item.get('obra_actual_nombre')
        st.info(f"Seleccionado: {item.get('marca','')} {item['nombre']} | {item['tipo']} | Obra actual: {current_obra or 'Sin obra'}")
        with st.form("movement_form"):
            obras_list = df_obras['nombre'].tolist()
            obra_destino = st.selectbox("* Obra destino", obras_list if obras_list else ["(Sin obras registradas)"])
            nueva_obra = st.text_input("¿Nueva obra?", placeholder="Nombre de nueva obra")
            responsable = st.text_input("* Responsable")
            motivo = st.selectbox("Motivo", ["Traslado por necesidad de obra","Finalización de trabajo","Mantenimiento programado","Reasignación de recursos","Otros"])
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
                        get_or_create_obra_id(nueva_obra.strip()); load_obras_data.clear()
                    motivo_final = motivo_custom if motivo == "Otros" and motivo_custom else motivo
                    if register_movement(item_id, current_obra, obra_final, responsable, motivo_final, observaciones):
                        st.success("✅ Movimiento registrado exitosamente!")
                        st.experimental_rerun()

def render_reports():
    st.subheader("📈 Reportes y Análisis")
    df_movs = pd.DataFrame(load_movimientos_data()); df_stock = pd.DataFrame(load_stock_data())
    if not df_movs.empty:
        t1, t2, t3 = st.tabs(["📊 Estadísticas","📋 Historial Completo","🔍 Filtros Avanzados"])
        with t1:
            st.write("**Movimientos por día (últimos 30)**")
            df_movs['fecha'] = pd.to_datetime(df_movs['fecha_movimiento']).dt.date
            st.bar_chart(df_movs['fecha'].value_counts().sort_index().tail(30))
            st.write("**Herramientas más movidas**")
            st.bar_chart(df_movs['item_nombre'].value_counts().head(10))
        with t2:
            st.dataframe(df_movs[['fecha_movimiento','item_marca','item_nombre','obra_origen_nombre','obra_destino_nombre','responsable','motivo']], use_container_width=True)
        with t3:
            col1,col2,col3 = st.columns(3)
            with col1: resp = st.selectbox("Filtrar por responsable", ["Todos"] + df_movs['responsable'].dropna().unique().tolist())
            with col2: item = st.selectbox("Filtrar por herramienta", ["Todos"] + df_movs['item_nombre'].dropna().unique().tolist())
            with col3: fdesde = st.date_input("Desde fecha")
            df_f = df_movs.copy()
            if resp != "Todos": df_f = df_f[df_f['responsable']==resp]
            if item != "Todos": df_f = df_f[df_f['item_nombre']==item]
            if fdesde: df_f = df_f[pd.to_datetime(df_f['fecha_movimiento']).dt.date >= fdesde]
            st.write(f"**Resultados filtrados ({len(df_f)} registros)**")
            if not df_f.empty:
                st.dataframe(df_f[['fecha_movimiento','item_marca','item_nombre','obra_origen_nombre','obra_destino_nombre','responsable','motivo']], use_container_width=True)
            else:
                st.info("No se encontraron registros con los filtros aplicados")
    else:
        st.info("No hay movimientos registrados para generar reportes")

def main():
    st.sidebar.title("🧭 Navegación")
    try:
        conn = init_connection(); ok = conn is not None
    except Exception:
        ok = False
    st.sidebar.markdown("🟢 **Conectado**" if ok else "🔴 **Desconectado**")
    page = st.sidebar.radio("Ir a:", ["📊 Dashboard","➕ Agregar Item","🚚 Registrar Movimiento","📋 Ver Stock","📈 Reportes"])
    if page == "📊 Dashboard": render_dashboard()
    elif page == "➕ Agregar Item": render_add_item()
    elif page == "🚚 Registrar Movimiento": render_register_movement()
    elif page == "📋 Ver Stock": render_stock_page()
    else: render_reports()

if __name__ == "__main__":
    main()
