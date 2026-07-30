import sqlite3
import pandas as pd
import streamlit as st
import datetime

# Configuración visual de la página
st.set_page_config(page_title="Control Go - Operaciones", layout="wide")

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
    </style>
""", unsafe_allow_html=True)

# 1. MOTOR DE BASE DE DATOS (VERSIÓN 2 - Estructura Completa Excel)
def inicializar_bd():
    with sqlite3.connect('control_go_v2.db') as conn:
        cursor = conn.cursor()
        # Tabla de inventario
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (sku TEXT PRIMARY KEY, nombre TEXT, stock_actual INTEGER, punto_reorden INTEGER)''')
        # Nueva estructura de la tabla de pedidos
        cursor.execute('''CREATE TABLE IF NOT EXISTS pedidos (
            id_pedido TEXT PRIMARY KEY, 
            fecha_pedido TEXT, 
            fecha_entrega TEXT, 
            nombre TEXT, 
            celular TEXT, 
            medio TEXT, 
            monto REAL, 
            direccion TEXT, 
            producto TEXT, 
            business TEXT, 
            estado TEXT DEFAULT 'Pendiente'
        )''')
        conn.commit()

inicializar_bd()

# 2. INTERFAZ VISUAL
st.title("📦 Panel de Control Operativo")

tab1, tab2, tab3 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas y Despachos", "⚠️ Alertas de Inventario"])

# --- PESTAÑA 1: AGENDAR (Celdas Interactivas y Desplegables) ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Completa las celdas. Haz doble clic para usar los calendarios y menús desplegables.")
    
    # Lista de opciones para los desplegables
    opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB"]
    opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]
    
    # Crear tabla vacía con las columnas exactas de tu Excel
    df_base = pd.DataFrame(columns=[
        "id_pedido", "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "medio", "monto", "direccion", "producto", "business"
    ])
    
    # Configurar el editor de celdas
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        column_config={
            "id_pedido": st.column_config.TextColumn("ID", required=True),
            "fecha_pedido": st.column_config.DateColumn("Fecha Pedido", format="YYYY-MM-DD"),
            "fecha_entrega": st.column_config.DateColumn("Fecha Entrega", format="YYYY-MM-DD"),
            "nombre": st.column_config.TextColumn("Nombre del Cliente", required=True),
            "celular": st.column_config.TextColumn("Celular"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio, required=True),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f", min_value=0.0),
            "direccion": st.column_config.TextColumn("Dirección"),
            "producto": st.column_config.TextColumn("Producto (Ej: 1 SKU1 + 3 SKU2)", required=True),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business, required=True)
        },
        use_container_width=True
    )
    
    # Guardar en base de datos
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['id_pedido', 'nombre', 'producto'], how='any')
        
        if not df_limpio.empty:
            try:
                # Convertir fechas a texto para que la base de datos las guarde bien
                df_limpio['fecha_pedido'] = df_limpio['fecha_pedido'].astype(str)
                df_limpio['fecha_entrega'] = df_limpio['fecha_entrega'].astype(str)
                df_limpio['estado'] = 'Pendiente'
                
                with sqlite3.connect('control_go_v2.db') as conn:
                    df_limpio.to_sql('pedidos', conn, if_exists='append', index=False)
                st.success("✅ Pedidos agendados correctamente con todos los detalles financieros y logísticos.")
            except Exception as e:
                st.error(f"⚠️ Error. Asegúrate de no repetir el ID de un pedido ya registrado. Detalle: {e}")
        else:
            st.warning("⚠️ Rellena al menos los campos obligatorios (ID, Nombre, Producto) antes de guardar.")

# --- PESTAÑA 2: DESPACHOS ---
with tab2:
    st.header("Gestión de Entregas")
    
    with sqlite3.connect('control_go_v2.db') as conn:
        # Traemos todas las columnas para que el área de rutas tenga el panorama completo
        query = """
        SELECT id_pedido, fecha_entrega, nombre, celular, direccion, medio, producto, monto, business 
        FROM pedidos WHERE estado = 'Pendiente'
        """
        df_pendientes = pd.read_sql_query(query, conn)
    
    if not df_pendientes.empty:
        st.dataframe(df_pendientes, use_container_width=True)
        
        st.subheader("Actualizar Estado")
        col1, col2, col3 = st.columns(3)
        with col1:
            id_actualizar = st.selectbox("ID del Paquete", df_pendientes['id_pedido'])
        with col2:
            nuevo_estado = st.selectbox("Nuevo Estado", ["Entregado", "Armado", "Anulado"])
        with col3:
            st.write("") 
            st.write("")
            if st.button("Guardar Cambio"):
                with sqlite3.connect('control_go_v2.db') as conn:
                    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (nuevo_estado, id_actualizar))
                    conn.commit()
                st.success("✅ Actualizado.")
                st.rerun()
    else:
        st.info("No hay paquetes pendientes de despacho.")

# --- PESTAÑA 3: INVENTARIO ---
with tab3:
    st.header("Control de Stock y Reposición")
    st.info("El sistema está preparado para leer la sintaxis de '1 SKU1 + 3 SKU2' y descontar unidades múltiples en la siguiente fase de desarrollo.")
