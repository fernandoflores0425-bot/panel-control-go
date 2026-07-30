import sqlite3
import pandas as pd
import streamlit as st
import datetime

# Configuración visual de la página
st.set_page_config(page_title="Control Go - Operaciones", layout="wide")

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

# Lista global de opciones (para usarse en ambas pestañas)
opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB"]
opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]
opciones_estado = ["POR ARMAR", "ARMADO", "ENTREGADO", "ANULADO", "DEVOLUCION", "REAGENDADO"]

# 1. MOTOR DE BASE DE DATOS (VERSIÓN 4)
def inicializar_bd():
    with sqlite3.connect('control_go_v4.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (sku TEXT PRIMARY KEY, nombre TEXT, stock_actual INTEGER, punto_reorden INTEGER)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS pedidos (
            id_pedido TEXT PRIMARY KEY, 
            fecha_pedido TEXT, 
            fecha_entrega TEXT, 
            nombre TEXT, 
            celular TEXT, 
            distrito TEXT,
            medio TEXT, 
            monto REAL, 
            direccion TEXT, 
            producto TEXT, 
            business TEXT,
            observaciones TEXT, 
            estado TEXT DEFAULT 'POR ARMAR'
        )''')
        conn.commit()

inicializar_bd()

# 2. INTERFAZ VISUAL
st.title("📦 Panel de Control Operativo")

tab1, tab2, tab3 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas por Día", "⚠️ Alertas de Inventario"])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Copia y pega desde tu Excel. Observaciones al final.")
    
    # Agregado "observaciones" al final
    df_base = pd.DataFrame(columns=[
        "id_pedido", "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"
    ])
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        column_config={
            "id_pedido": st.column_config.TextColumn("ID", required=True),
            "fecha_pedido": st.column_config.TextColumn("Fecha Pedido (DD/MM/YYYY)"),
            "fecha_entrega": st.column_config.TextColumn("Fecha Entrega (DD/MM/YYYY)"),
            "nombre": st.column_config.TextColumn("Nombre del Cliente", required=True),
            "celular": st.column_config.TextColumn("Celular"),
            "distrito": st.column_config.TextColumn("Distrito"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio, required=True),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f", min_value=0.0),
            "direccion": st.column_config.TextColumn("Dirección"),
            "producto": st.column_config.TextColumn("Producto", required=True),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business, required=True),
            "observaciones": st.column_config.TextColumn("Observaciones")
        },
        use_container_width=True
    )
    
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['id_pedido'], how='any')
        
        if not df_limpio.empty:
            try:
                # El estado inicial ahora es "POR ARMAR"
                df_limpio['estado'] = 'POR ARMAR'
                with sqlite3.connect('control_go_v4.db') as conn:
                    df_limpio.to_sql('pedidos', conn, if_exists='append', index=False)
                st.success("✅ Pedidos agendados correctamente.")
            except Exception as e:
                st.error(f"⚠️ Error. Asegúrate de no repetir el ID. Detalle: {e}")
        else:
            st.warning("⚠️ Rellena al menos el campo de ID antes de guardar.")

# --- PESTAÑA 2: RUTAS Y DESPACHOS (VISIÓN 2x2) ---
with tab2:
    st.header("Torre de Control de Despachos")
    
    # Selector de fecha (Por defecto: la fecha de hoy en formato DD/MM/YYYY)
    fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    fecha_filtro = st.text_input("📅 Fecha de ruta a procesar (DD/MM/YYYY):", value=fecha_hoy)
    
    # Multiselector para elegir los paneles a visualizar
    medios_seleccionados = st.multiselect(
        "Selecciona hasta 4 Courier/Medios para visualizar:", 
        options=opciones_medio, 
        default=["MD", "ENTRE GO", "URB", "PROV"], 
        max_selections=4
    )
    
    st.markdown("---")
    
    if medios_seleccionados:
        # Crea la cuadrícula de 2 columnas (para el efecto 2 arriba, 2 abajo)
        columnas = st.columns(2)
        
        for i, medio in enumerate(medios_seleccionados):
            # i % 2 distribuye alternadamente: panel 1 a la izq, panel 2 a la der, panel 3 a la izq...
            with columnas[i % 2]:
                st.subheader(f"🚚 {medio}")
                
                with sqlite3.connect('control_go_v4.db') as conn:
                    # Lógica estricta: Mostrar si es la fecha seleccionada O si está REAGENDADO. 
                    # NUNCA mostrar si ya se entregó, anuló o devolvió.
                    query = """
                    SELECT id_pedido, nombre, celular, distrito, monto, producto, business, estado 
                    FROM pedidos 
                    WHERE medio = ? 
                    AND (fecha_entrega = ? OR estado = 'REAGENDADO')
                    AND estado NOT IN ('ENTREGADO', 'ANULADO', 'DEVOLUCION')
                    """
                    df_medio = pd.read_sql_query(query, conn, params=(medio, fecha_filtro))
                
                if not df_medio.empty:
                    # Tabla editable directo en pantalla
                    df_rutas = st.data_editor(
                        df_medio,
                        key=f"editor_{medio}",
                        # Bloqueamos todas las celdas para que no las borren por error, EXCEPTO el 'estado'
                        disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "producto", "business"],
                        column_config={
                            "estado": st.column_config.SelectboxColumn(
                                "Estado", 
                                options=opciones_estado, 
                                required=True
                            )
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # Botón individual para guardar cada cuadrícula
                    if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                        with sqlite3.connect('control_go_v4.db') as conn:
                            cambios = 0
                            for index, row in df_rutas.iterrows():
                                # Solo impacta la base de datos si cambiaste algo en el menú desplegable
                                if row['estado'] != df_medio.loc[index, 'estado']:
                                    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (row['estado'], row['id_pedido']))
                                    cambios += 1
                                    
                            if cambios > 0:
                                conn.commit()
                                st.success(f"✅ Se actualizaron {cambios} estados en {medio}.")
                                st.rerun() # Refresca para limpiar de la pantalla los que ya se entregaron
                            else:
                                st.info("No detecté cambios.")
                else:
                    st.info(f"Ruta limpia. No hay paquetes pendientes para {medio} hoy.")
                
                st.write("") # Espaciador inferior
                st.write("")
    else:
        st.warning("Selecciona al menos un medio de envío para ver sus rutas.")

# --- PESTAÑA 3: INVENTARIO ---
with tab3:
    st.header("Control de Stock y Reposición")
    st.info("El sistema está preparado para leer la sintaxis de '1 SKU1 + 3 SKU2' y descontar unidades múltiples en la siguiente fase de desarrollo.")
