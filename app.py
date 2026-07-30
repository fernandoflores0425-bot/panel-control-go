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

opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB", "GOATE"]
opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]
opciones_estado = ["POR ARMAR", "ARMADO", "ENTREGADO", "ANULADO", "DEVOLUCION", "REAGENDADO"]

# 1. MOTOR DE BASE DE DATOS
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

# ¡AQUÍ ESTÁ EL CAMBIO! Agregamos una cuarta pestaña para Editar
tab1, tab2, tab3, tab4 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", "⚠️ Alertas de Inventario"])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Copia de tu Excel y pega directo en la primera celda. Los IDs se generarán automáticamente.")
    
    df_base = pd.DataFrame(index=range(15), columns=[
        "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"
    ])
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        column_config={
            "fecha_pedido": st.column_config.TextColumn("Fecha Pedido (DD/MM/YYYY)"),
            "fecha_entrega": st.column_config.TextColumn("Fecha Entrega (DD/MM/YYYY)"),
            "nombre": st.column_config.TextColumn("Nombre del Cliente"),
            "celular": st.column_config.TextColumn("Celular"),
            "distrito": st.column_config.TextColumn("Distrito"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f", min_value=0.0),
            "direccion": st.column_config.TextColumn("Dirección"),
            "producto": st.column_config.TextColumn("Producto"),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business),
            "observaciones": st.column_config.TextColumn("Observaciones")
        },
        use_container_width=True
    )
    
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['nombre', 'producto'], how='any').copy()
        
        if not df_limpio.empty:
            try:
                for col in df_limpio.columns:
                    if df_limpio[col].dtype == 'object':
                        df_limpio[col] = df_limpio[col].astype(str).str.strip()
                
                with sqlite3.connect('control_go_v4.db') as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id_pedido FROM pedidos ORDER BY ROWID DESC LIMIT 1")
                    ultimo_registro = cursor.fetchone()
                    
                    if ultimo_registro and ultimo_registro[0].startswith("CG-"):
                        try:
                            ultimo_numero = int(ultimo_registro[0].split("-")[1])
                        except ValueError:
                            ultimo_numero = 1000
                    else:
                        ultimo_numero = 1000 
                    
                    nuevos_ids = []
                    for i in range(len(df_limpio)):
                        ultimo_numero += 1
                        nuevos_ids.append(f"CG-{ultimo_numero}")
                    
                    df_limpio.insert(0, 'id_pedido', nuevos_ids)
                    df_limpio['estado'] = 'POR ARMAR'
                    
                    df_limpio.to_sql('pedidos', conn, if_exists='append', index=False)
                st.success(f"✅ ¡{len(df_limpio)} pedidos agendados exitosamente! Se generaron los códigos desde {nuevos_ids[0]} hasta {nuevos_ids[-1]}.")
            except Exception as e:
                st.error(f"⚠️ Error al procesar. Detalle: {e}")
        else:
            st.warning("⚠️ La tabla está vacía o faltan datos obligatorios (Nombre y Producto).")

# --- PESTAÑA 2: RUTAS Y DESPACHOS ---
with tab2:
    st.header("Torre de Control de Despachos")
    
    with sqlite3.connect('control_go_v4.db') as conn:
        fechas_df = pd.read_sql_query("SELECT DISTINCT fecha_entrega FROM pedidos WHERE estado NOT IN ('ENTREGADO', 'ANULADO', 'DEVOLUCION') AND fecha_entrega IS NOT NULL", conn)
    
    lista_fechas = [f.strip() for f in fechas_df['fecha_entrega'].astype(str).tolist() if f.strip() != "nan" and f.strip() != "None" and f.strip() != ""]
    
    if not lista_fechas:
        lista_fechas = [datetime.datetime.now().strftime("%d/%m/%Y")]
        st.info("No se detectaron fechas agendadas pendientes.")
        
    fecha_filtro = st.selectbox("📅 Selecciona la fecha de ruta a procesar:", options=lista_fechas)
    
    medios_seleccionados = st.multiselect(
        "Selecciona hasta 4 Courier/Medios para visualizar:", 
        options=opciones_medio, 
        default=["MD", "ENTRE GO", "URB", "PROV"], 
        max_selections=4
    )
    
    st.markdown("---")
    
    if medios_seleccionados:
        columnas = st.columns(2)
        
        for i, medio in enumerate(medios_seleccionados):
            with columnas[i % 2]:
                st.subheader(f"🚚 {medio}")
                
                with sqlite3.connect('control_go_v4.db') as conn:
                    query = """
                    SELECT id_pedido, nombre, celular, distrito, monto, producto, business, estado 
                    FROM pedidos 
                    WHERE medio = ? 
                    AND (fecha_entrega = ? OR estado = 'REAGENDADO')
                    AND estado NOT IN ('ENTREGADO', 'ANULADO', 'DEVOLUCION')
                    """
                    df_medio = pd.read_sql_query(query, conn, params=(medio, fecha_filtro))
                
                if not df_medio.empty:
                    df_rutas = st.data_editor(
                        df_medio,
                        key=f"editor_{medio}",
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
                    
                    if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                        with sqlite3.connect('control_go_v4.db') as conn:
                            cambios = 0
                            for index, row in df_rutas.iterrows():
                                if row['estado'] != df_medio.loc[index, 'estado']:
                                    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (row['estado'], row['id_pedido']))
                                    cambios += 1
                                    
                            if cambios > 0:
                                conn.commit()
                                st.success(f"✅ Se actualizaron {cambios} estados en {medio}.")
                                st.rerun() 
                            else:
                                st.info("No detecté cambios.")
                else:
                    st.info(f"Ruta limpia. No hay paquetes pendientes.")
                
                st.write("") 
                st.write("")
    else:
        st.warning("Selecciona al menos un medio de envío.")

# --- PESTAÑA 3: BUSCAR Y EDITAR ---
with tab3:
    st.header("✏️ Buscador y Edición de Pedidos")
    st.write("Busca cualquier pedido por su ID, Nombre o Celular para corregir errores, cambiar el courier o agregar productos.")
    
    # Barra de búsqueda
    busqueda = st.text_input("🔍 Buscar pedido (deja en blanco para ver los últimos 20 registrados):")
    
    with sqlite3.connect('control_go_v4.db') as conn:
        if busqueda:
            # Busca coincidencias en ID, nombre o celular
            query = "SELECT * FROM pedidos WHERE id_pedido LIKE ? OR nombre LIKE ? OR celular LIKE ? ORDER BY ROWID DESC"
            df_editar = pd.read_sql_query(query, conn, params=(f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"))
        else:
            # Si no hay búsqueda, muestra los últimos 20
            query = "SELECT * FROM pedidos ORDER BY ROWID DESC LIMIT 20"
            df_editar = pd.read_sql_query(query, conn)
            
    if not df_editar.empty:
        # Mostramos la tabla completamente editable (excepto el ID)
        df_editado_global = st.data_editor(
            df_editar,
            key="editor_global",
            use_container_width=True,
            hide_index=True,
            disabled=["id_pedido"], # Bloqueamos el ID para no romper la base de datos
            column_config={
                "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio),
                "business": st.column_config.SelectboxColumn("Business", options=opciones_business),
                "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado)
            }
        )
        
        if st.button("💾 Guardar Ediciones"):
            with sqlite3.connect('control_go_v4.db') as conn:
                for index, row in df_editado_global.iterrows():
                    # Actualiza todos los campos de esa fila específica
                    conn.execute("""
                        UPDATE pedidos 
                        SET fecha_pedido=?, fecha_entrega=?, nombre=?, celular=?, distrito=?, 
                            medio=?, monto=?, direccion=?, producto=?, business=?, observaciones=?, estado=?
                        WHERE id_pedido=?
                    """, (
                        row['fecha_pedido'], row['fecha_entrega'], row['nombre'], row['celular'], row['distrito'],
                        row['medio'], row['monto'], row['direccion'], row['producto'], row['business'], 
                        row['observaciones'], row['estado'], row['id_pedido']
                    ))
                conn.commit()
            st.success("✅ Cambios guardados correctamente.")
            st.rerun() # Refresca la página para mostrar los datos actualizados
    else:
        st.info("No se encontraron pedidos con esa búsqueda.")

# --- PESTAÑA 4: INVENTARIO ---
with tab4:
    st.header("Control de Stock y Reposición")
    st.info("El sistema está preparado para leer la sintaxis de '1 SKU1 + 3 SKU2' y descontar unidades múltiples en la siguiente fase de desarrollo.")
