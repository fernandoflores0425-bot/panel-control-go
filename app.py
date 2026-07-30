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
    with sqlite3.connect('control_go_v5.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (
            sku TEXT PRIMARY KEY, 
            nombre TEXT, 
            stock_actual INTEGER, 
            precio REAL,
            stock_minimo INTEGER,
            stock_ideal INTEGER
        )''')
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

# MOTOR DE LECTURA (ACTUALIZADO PARA IGNORAR "PLS")
def decodificar_productos(producto_str):
    articulos = []
    if not producto_str or pd.isna(producto_str): return articulos
    
    partes = str(producto_str).split('+')
    for p in partes:
        p = p.strip()
        if not p: 
            continue
            
        # Filtro 1: Si escriben exactamente "PLS" o "pls"
        if p.upper() == 'PLS':
            continue
            
        if ' ' in p:
            cant_str, sku = p.split(' ', 1)
            sku = sku.strip()
            
            # Filtro 2: Si escriben cantidad antes de las pilas, ej: "2 PLS"
            if sku.upper() == 'PLS':
                continue
                
            try:
                articulos.append({'sku': sku, 'cant': int(cant_str)})
            except ValueError:
                articulos.append({'sku': p, 'cant': 1})
        else:
            articulos.append({'sku': p, 'cant': 1})
    return articulos

# 2. INTERFAZ VISUAL
st.title("📦 Panel de Control Operativo")

tab1, tab2, tab3, tab4 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", "📊 Maestro de Inventario"])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("El sistema verificará los SKUs. Usa el formato '1 SKU1 + 3 SKU2 + PLS'. Las pilas (PLS) se ignorarán automáticamente.")
    
    df_base = pd.DataFrame(index=range(15), columns=[
        "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"
    ])
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        column_config={
            "fecha_pedido": st.column_config.TextColumn("Fecha Pedido"),
            "fecha_entrega": st.column_config.TextColumn("Fecha Entrega"),
            "nombre": st.column_config.TextColumn("Nombre"),
            "celular": st.column_config.TextColumn("Celular"),
            "distrito": st.column_config.TextColumn("Distrito"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f"),
            "direccion": st.column_config.TextColumn("Dirección"),
            "producto": st.column_config.TextColumn("Producto"),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business),
            "observaciones": st.column_config.TextColumn("Obs.")
        },
        use_container_width=True
    )
    
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['nombre', 'producto'], how='any').copy()
        
        if not df_limpio.empty:
            error_bloqueante = False
            alertas_stock = []
            operaciones_descuento = []
            
            with sqlite3.connect('control_go_v5.db') as conn:
                cursor = conn.cursor()
                
                for index, row in df_limpio.iterrows():
                    articulos_pedidos = decodificar_productos(row['producto'])
                    
                    for art in articulos_pedidos:
                        cursor.execute("SELECT stock_actual, stock_minimo FROM inventario WHERE sku = ?", (art['sku'],))
                        resultado = cursor.fetchone()
                        
                        if not resultado:
                            st.error(f"❌ ERROR: El producto '{art['sku']}' (Pedido de {row['nombre']}) NO existe en el Inventario Maestro. Agéndalo primero en la Pestaña 4.")
                            error_bloqueante = True
                            break
                        else:
                            stock_actual, stock_minimo = resultado
                            nuevo_stock = stock_actual - art['cant']
                            operaciones_descuento.append({'sku': art['sku'], 'nuevo_stock': nuevo_stock})
                            
                            if nuevo_stock < 0:
                                alertas_stock.append(f"⚠️ Atención: '{art['sku']}' quedó con stock negativo ({nuevo_stock}).")
                            elif nuevo_stock <= stock_minimo:
                                alertas_stock.append(f"🔔 Alerta: '{art['sku']}' llegó a su Stock Mínimo. Quedan {nuevo_stock} unidades.")
                
                if not error_bloqueante:
                    cursor.execute("SELECT id_pedido FROM pedidos ORDER BY ROWID DESC LIMIT 1")
                    ultimo_registro = cursor.fetchone()
                    ultimo_numero = int(ultimo_registro[0].split("-")[1]) if (ultimo_registro and ultimo_registro[0].startswith("CG-")) else 1000
                    
                    nuevos_ids = []
                    for _ in range(len(df_limpio)):
                        ultimo_numero += 1
                        nuevos_ids.append(f"CG-{ultimo_numero}")
                    
                    df_limpio.insert(0, 'id_pedido', nuevos_ids)
                    df_limpio['estado'] = 'POR ARMAR'
                    
                    df_limpio.to_sql('pedidos', conn, if_exists='append', index=False)
                    
                    for op in operaciones_descuento:
                        cursor.execute("UPDATE inventario SET stock_actual = ? WHERE sku = ?", (op['nuevo_stock'], op['sku']))
                    
                    conn.commit()
                    st.success("✅ Pedidos registrados y stock descontado con éxito.")
                    
                    for alerta in set(alertas_stock): 
                        st.warning(alerta)
        else:
            st.warning("⚠️ La tabla está vacía.")

# --- PESTAÑA 2: RUTAS Y DESPACHOS ---
with tab2:
    st.header("Torre de Control de Despachos")
    with sqlite3.connect('control_go_v5.db') as conn:
        fechas_df = pd.read_sql_query("SELECT DISTINCT fecha_entrega FROM pedidos WHERE estado NOT IN ('ENTREGADO', 'ANULADO', 'DEVOLUCION') AND fecha_entrega IS NOT NULL", conn)
    
    lista_fechas = [f.strip() for f in fechas_df['fecha_entrega'].astype(str).tolist() if f.strip() != "nan" and f.strip() != "None" and f.strip() != ""]
    if not lista_fechas: lista_fechas = [datetime.datetime.now().strftime("%d/%m/%Y")]
        
    fecha_filtro = st.selectbox("📅 Selecciona la fecha de ruta a procesar:", options=lista_fechas)
    medios_seleccionados = st.multiselect("Courier:", options=opciones_medio, default=["MD", "ENTRE GO", "URB", "PROV"], max_selections=4)
    
    if medios_seleccionados:
        columnas = st.columns(2)
        for i, medio in enumerate(medios_seleccionados):
            with columnas[i % 2]:
                st.subheader(f"🚚 {medio}")
                with sqlite3.connect('control_go_v5.db') as conn:
                    df_medio = pd.read_sql_query("SELECT id_pedido, nombre, celular, distrito, monto, producto, business, estado FROM pedidos WHERE medio = ? AND (fecha_entrega = ? OR estado = 'REAGENDADO') AND estado NOT IN ('ENTREGADO', 'ANULADO', 'DEVOLUCION')", conn, params=(medio, fecha_filtro))
                
                if not df_medio.empty:
                    df_rutas = st.data_editor(df_medio, key=f"editor_{medio}", disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "producto", "business"], column_config={"estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado, required=True)}, use_container_width=True, hide_index=True)
                    if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                        with sqlite3.connect('control_go_v5.db') as conn:
                            for index, row in df_rutas.iterrows():
                                if row['estado'] != df_medio.loc[index, 'estado']:
                                    conn.execute("UPDATE pedidos SET estado = ? WHERE id_pedido = ?", (row['estado'], row['id_pedido']))
                            conn.commit()
                        st.rerun() 
                else:
                    st.info("Ruta limpia.")

# --- PESTAÑA 3: BUSCAR Y EDITAR ---
with tab3:
    st.header("✏️ Buscador y Edición de Pedidos")
    busqueda = st.text_input("🔍 Buscar pedido (por ID, Nombre o Celular):")
    with sqlite3.connect('control_go_v5.db') as conn:
        if busqueda:
            df_editar = pd.read_sql_query("SELECT * FROM pedidos WHERE id_pedido LIKE ? OR nombre LIKE ? OR celular LIKE ? ORDER BY ROWID DESC", conn, params=(f"%{busqueda}%", f"%{busqueda}%", f"%{busqueda}%"))
        else:
            df_editar = pd.read_sql_query("SELECT * FROM pedidos ORDER BY ROWID DESC LIMIT 20", conn)
            
    if not df_editar.empty:
        df_editado_global = st.data_editor(df_editar, key="editor_global", use_container_width=True, hide_index=True, disabled=["id_pedido"], column_config={"medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio), "business": st.column_config.SelectboxColumn("Business", options=opciones_business), "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado)})
        if st.button("💾 Guardar Ediciones"):
            with sqlite3.connect('control_go_v5.db') as conn:
                for index, row in df_editado_global.iterrows():
                    conn.execute("UPDATE pedidos SET fecha_pedido=?, fecha_entrega=?, nombre=?, celular=?, distrito=?, medio=?, monto=?, direccion=?, producto=?, business=?, observaciones=?, estado=? WHERE id_pedido=?", (row['fecha_pedido'], row['fecha_entrega'], row['nombre'], row['celular'], row['distrito'], row['medio'], row['monto'], row['direccion'], row['producto'], row['business'], row['observaciones'], row['estado'], row['id_pedido']))
                conn.commit()
            st.success("✅ Cambios guardados correctamente.")
            st.rerun()

# --- PESTAÑA 4: INVENTARIO (MAESTRO Y REPOSICIÓN) ---
with tab4:
    st.header("📊 Maestro de Inventario y Alertas")
    st.write("Pega aquí tu lista maestra. El sistema calculará cuánto debes reponer según tu Stock Ideal.")
    
    with sqlite3.connect('control_go_v5.db') as conn:
        df_inv = pd.read_sql_query("SELECT nombre, sku, stock_actual, precio, stock_minimo, stock_ideal FROM inventario", conn)
    
    if df_inv.empty:
        df_inv = pd.DataFrame(index=range(10), columns=["nombre", "sku", "stock_actual", "precio", "stock_minimo", "stock_ideal"])
    
    df_inv_editado = st.data_editor(
        df_inv,
        num_rows="dynamic",
        column_config={
            "nombre": st.column_config.TextColumn("Nombre del Producto", required=True),
            "sku": st.column_config.TextColumn("SKU (Código único)", required=True),
            "stock_actual": st.column_config.NumberColumn("Stock Disponible", min_value=0, step=1, required=True),
            "precio": st.column_config.NumberColumn("Precio", format="S/ %.2f"),
            "stock_minimo": st.column_config.NumberColumn("Stock Mínimo (Alerta)", min_value=0, step=1),
            "stock_ideal": st.column_config.NumberColumn("Stock Ideal (Meta)", min_value=0, step=1)
        },
        use_container_width=True,
        height=400
    )
    
    if st.button("💾 Guardar y Actualizar Inventario"):
        df_inv_limpio = df_inv_editado.dropna(subset=['sku', 'nombre'], how='any').copy()
        
        # 1. LIMPIEZA INTELIGENTE: Quitar espacios en blanco de los SKUs
        df_inv_limpio['sku'] = df_inv_limpio['sku'].astype(str).str.strip()
        
        # 2. FILTRO ANTI-DUPLICADOS: Si hay dos SKUs iguales, nos quedamos con el último
        if df_inv_limpio.duplicated(subset=['sku']).any():
            st.warning("⚠️ Se detectaron SKUs duplicados. El sistema unificó los repetidos automáticamente.")
            df_inv_limpio = df_inv_limpio.drop_duplicates(subset=['sku'], keep='last')

        df_inv_limpio['stock_actual'] = pd.to_numeric(df_inv_limpio['stock_actual'], errors='coerce').fillna(0).astype(int)
        df_inv_limpio['stock_minimo'] = pd.to_numeric(df_inv_limpio['stock_minimo'], errors='coerce').fillna(0).astype(int)
        df_inv_limpio['stock_ideal'] = pd.to_numeric(df_inv_limpio['stock_ideal'], errors='coerce').fillna(0).astype(int)
        
        try:
            with sqlite3.connect('control_go_v5.db') as conn:
                conn.execute("DELETE FROM inventario")
                df_inv_limpio.to_sql('inventario', conn, if_exists='append', index=False)
            st.success("✅ Maestro de inventario actualizado correctamente.")
            st.rerun()
        except Exception as e:
            # Si vuelve a ocurrir un error, ahora el sistema te mostrará exactamente qué lo causó sin colapsar
            st.error(f"❌ Error al guardar. Revisa que no haya datos inválidos. Detalle técnico: {e}")

    st.markdown("---")
    st.subheader("🛒 Panel de Compras (Reposición)")
    
    if not df_inv.empty:
        df_critico = df_inv[df_inv['stock_actual'] <= df_inv['stock_minimo']].copy()
        
        if not df_critico.empty:
            df_critico['A Comprar'] = df_critico['stock_ideal'] - df_critico['stock_actual']
            df_critico['A Comprar'] = df_critico['A Comprar'].apply(lambda x: x if x > 0 else 0)
            
            st.error(f"⚠️ Tienes {len(df_critico)} productos en nivel crítico (Igual o menor al Stock Mínimo).")
            
            st.dataframe(
                df_critico[['sku', 'nombre', 'stock_actual', 'stock_minimo', 'stock_ideal', 'A Comprar']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("✅ Tu inventario está sano. Ningún producto ha tocado su nivel de alerta mínima.")
