import sqlite3
import pandas as pd
import streamlit as st
import io

# Configuración visual de la página
st.set_page_config(page_title="Gestión Operativa", layout="wide")

# Diseño corporativo (Minimalista B/N con acentos turquesa)
st.markdown("""
    <style>
    .stButton>button {
        background-color: #40E0D0;
        color: black;
        font-weight: bold;
        border-radius: 5px;
        border: 1px solid #000000;
    }
    .stTextInput>div>div>input {
        border: 1px solid #000000;
    }
    </style>
""", unsafe_allow_html=True)

# 1. MOTOR DE BASE DE DATOS
def inicializar_bd():
    with sqlite3.connect('base_datos.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (sku TEXT PRIMARY KEY, nombre TEXT, stock_actual INTEGER, punto_reorden INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS pedidos (id_pedido TEXT PRIMARY KEY, cliente TEXT, distrito TEXT, sku TEXT, cantidad INTEGER, estado TEXT DEFAULT 'Pendiente')''')
        conn.commit()

inicializar_bd()

# 2. INTERFAZ VISUAL
st.title("📦 Panel de Control Operativo")

# Pestañas de navegación
tab1, tab2, tab3 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas y Despachos", "⚠️ Alertas de Inventario"])

# --- PESTAÑA 1: AGENDAR (Celdas Interactivas) ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Escribe o pega tus datos directamente en las celdas. Usa el botón '+' para agregar más filas.")
    
    # 1. Generar estructura base de la tabla
    df_base = pd.DataFrame(columns=["id_pedido", "cliente", "distrito", "sku", "cantidad"])
    
    # 2. Activar el editor de celdas (estilo Excel)
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic", # Permite agregar filas dinámicamente
        use_container_width=True
    )
    
    # 3. Botón de registro
    if st.button("Registrar Pedidos"):
        # Limpiar filas que se hayan dejado en blanco por error
        df_limpio = df_editado.dropna(how='all')
        
        if not df_limpio.empty:
            try:
                df_limpio['estado'] = 'Pendiente'
                with sqlite3.connect('base_datos.db') as conn:
                    df_limpio.to_sql('pedidos', conn, if_exists='append', index=False)
                st.success("✅ Pedidos agendados correctamente. Revisa la pestaña de Despachos.")
            except Exception as e:
                st.error(f"⚠️ Error al procesar. Verifica que el ID no esté duplicado en la base de datos.")
        else:
            st.warning("⚠️ La tabla está vacía. Agrega al menos un pedido antes de registrar.")

# --- PESTAÑA 2: DESPACHOS ---
with tab2:
    st.header("Gestión de Entregas")
    
    with sqlite3.connect('base_datos.db') as conn:
        df_pendientes = pd.read_sql_query("SELECT id_pedido, cliente, distrito, sku, cantidad FROM pedidos WHERE estado = 'Pendiente'", conn)
    
    if not df_pendientes.empty:
        st.dataframe(df_pendientes, use_container_width=True)
        
        st.subheader("Actualizar Estado")
        col1, col2, col3 = st.columns(3)
        with col1:
            id_actualizar = st.selectbox("ID del Paquete", df_pendientes['id_pedido'])
        with col2:
            nuevo_estado = st.selectbox("Nuevo Estado", ["Entregado", "Armado", "Anulado"])
        with col3:
            st.write("") # Espaciador
            st.write("")
            if st.button("Guardar Cambio"):
                with sqlite3.connect('base_datos.db') as conn:
                    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (nuevo_estado, id_actualizar))
                    conn.commit()
                st.success("✅ Actualizado.")
                st.rerun()
    else:
        st.info("No hay paquetes pendientes de despacho.")

# --- PESTAÑA 3: INVENTARIO ---
with tab3:
    st.header("Control de Stock y Reposición")
    st.info("Sistema de base de datos relacional activo y enlazado. Aquí se visualizará el stock de seguridad.")
