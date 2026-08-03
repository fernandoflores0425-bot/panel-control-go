import streamlit as st
import pandas as pd
import datetime
import re
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN VISUAL Y DE MEMORIA ---
st.set_page_config(page_title="Control Go - Operaciones", layout="wide")

if 'limpiador_tab1' not in st.session_state:
    st.session_state['limpiador_tab1'] = 0

if 'limpiador_ingreso' not in st.session_state:
    st.session_state['limpiador_ingreso'] = 0

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

# --- 2. CONEXIÓN BLINDADA A LA NUBE ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["SUPABASE_URL"].strip()
        key = st.secrets["SUPABASE_KEY"].strip()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error leyendo los Secrets: {e}")
        st.stop()

supabase = init_connection()

# --- 3. VARIABLES GLOBALES Y FUNCIONES ---
opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB", "GOATE"]
opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]

opciones_estado_general = ["POR ARMAR", "ARMADO", "EN RUTA", "ENTREGADO", "ANULADO", "DEVOLUCION", "REPROGRAMADO"]
opciones_estado_todas = ["POR ARMAR", "ARMADO", "EN RUTA", "POR RECOGER", "ENTREGADO", "ANULADO", "DEVOLUCION", "REPROGRAMADO"]

def decodificar_productos(producto_str):
    articulos = []
    if not producto_str or pd.isna(producto_str): return articulos
    partes = str(producto_str).split('+')
    for p in partes:
        p = p.strip()
        if not p or p.upper() == 'PLS': continue
        if ' ' in p:
            cant_str, sku = p.split(' ', 1)
            sku = sku.strip()
            if sku.upper() == 'PLS': continue
            try:
                articulos.append({'sku': sku, 'cant': int(cant_str)})
            except ValueError:
                articulos.append({'sku': p, 'cant': 1})
        else:
            articulos.append({'sku': p, 'cant': 1})
    return articulos

def resaltar_estados(row):
    color = ''
    if row['estado'] == 'ARMADO':
        color = 'background-color: #e8f5e9; color: black'
    elif row['estado'] == 'EN RUTA':
        color = 'background-color: #e3f2fd; color: black'
    elif row['estado'] == 'ENTREGADO':
        color = 'background-color: #cfd8dc; color: #546e7a'
    elif row['estado'] in ['ANULADO', 'DEVOLUCION']:
        color = 'background-color: #ffebee; color: black'
    elif row['estado'] == 'REPROGRAMADO':
        color = 'background-color: #fff3e0; color: black'
    return [color] * len(row)

@st.cache_data(show_spinner=False)
def descargar_datos_seguros(nombre_tabla):
    try:
        respuesta = supabase.table(nombre_tabla).select("*").execute()
        return respuesta.data
    except Exception as e:
        st.error(f"❌ ERROR CRÍTICO: No se pudo leer la tabla '{nombre_tabla}'. Detalle: {e}")
        return None

def procesar_fecha(valor):
    if pd.isna(valor) or valor == "":
        return ""
    if hasattr(valor, 'strftime'):
        return valor.strftime("%d/%m/%Y")
    return str(valor)

def procesar_cambio_estado_con_stock(id_pedido, estado_antiguo, estado_nuevo, producto_str):
    if estado_antiguo in ["POR ARMAR", "ARMADO", "REPROGRAMADO"] and estado_nuevo == "ANULADO":
        datos_inv = descargar_datos_seguros("inventario")
        if datos_inv:
            inventario_db = {item['sku']: item for item in datos_inv}
            articulos = decodificar_productos(producto_str)
            for art in articulos:
                if art['sku'] in inventario_db:
                    stock_actual = inventario_db[art['sku']]['stock_actual']
                    nuevo_stock = stock_actual + art['cant']
                    supabase.table("inventario").update({"stock_actual": nuevo_stock}).eq("sku", art['sku']).execute()
        return True 
    return False

# NUEVA FUNCIÓN: Ordenamiento Natural Alfanumérico
def clave_orden_natural(sku):
    # Divide "CAR10" en ["CAR", 10] para comparar lógicamente
    return [int(texto) if texto.isdigit() else texto.lower() for texto in re.split(r'(\d+)', str(sku))]

st.title("📦 Panel de Control Operativo")
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", 
    "📊 Maestro de Inventario", "📦 Shalom (Provincias)", "📥 Ingreso Mercadería"
])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    
    if 'msg_exito' in st.session_state:
        st.success(st.session_state['msg_exito'])
        del st.session_state['msg_exito']
    if 'msg_alertas' in st.session_state:
        for alerta in st.session_state['msg_alertas']:
            st.warning(alerta)
        del st.session_state['msg_alertas']

    st.write("Copia de tu Excel y pega directo en la primera celda.")
    
    df_base = pd.DataFrame(index=range(15), columns=[
        "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"
    ])
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        key=f"editor_pedidos_{st.session_state['limpiador_tab1']}",
        column_config={
            "fecha_pedido": st.column_config.DateColumn("Fecha Pedido", format="DD/MM/YYYY"),
            "fecha_entrega": st.column_config.DateColumn("Fecha Entrega", format="DD/MM/YYYY"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f"),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business),
        },
        use_container_width=True
    )
    
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['nombre', 'producto'], how='any').copy()
        
        if not df_limpio.empty:
            datos_inv = descargar_datos_seguros("inventario")
            if datos_inv is None:
                st.stop()
                
            inventario_db = {item['sku']: item for item in datos_inv}
            error_bloqueante = False
            operaciones_descuento = []
            alertas_stock = []
            
            for index, row in df_limpio.iterrows():
                articulos_pedidos = decodificar_productos(row['producto'])
                for art in articulos_pedidos:
                    if art['sku'] not in inventario_db:
                        st.error(f"❌ ERROR: El producto '{art['sku']}' NO existe en el Inventario.")
                        error_bloqueante = True
                        break
                    else:
                        item_inv = inventario_db[art['sku']]
                        stock_actual = item_inv['stock_actual']
                        stock_minimo = item_inv.get('stock_minimo', 0)
                        nuevo_stock = stock_actual - art['cant']
                        
                        operaciones_descuento.append({'sku': art['sku'], 'nuevo_stock': nuevo_stock})
                        
                        if nuevo_stock < 0:
                            alertas_stock.append(f"⚠️ Atención: '{art['sku']}' quedó con stock negativo ({nuevo_stock}).")
                        elif nuevo_stock <= stock_minimo:
                            alertas_stock.append(f"🔔 Alerta: '{art['sku']}' llegó a su límite. Quedan {nuevo_stock} unidades.")
            
            if not error_bloqueante:
                datos_pedidos = descargar_datos_seguros("pedidos")
                if datos_pedidos is None:
                    st.stop()
                
                ultimo_numero = 1000
                if datos_pedidos:
                    ids = [int(p['id_pedido'].replace("CG-", "")) for p in datos_pedidos if p['id_pedido'].startswith("CG-")]
                    if ids: ultimo_numero = max(ids)
                
                nuevos_registros = []
                for _, row in df_limpio.iterrows():
                    ultimo_numero += 1
                    nuevos_registros.append({
                        "id_pedido": f"CG-{ultimo_numero}",
                        "fecha_pedido": procesar_fecha(row['fecha_pedido']),
                        "fecha_entrega": procesar_fecha(row['fecha_entrega']),
                        "nombre": str(row['nombre']),
                        "celular": str(row['celular']),
                        "distrito": str(row['distrito']),
                        "medio": str(row['medio']),
                        "monto": float(row['monto']) if pd.notna(row['monto']) else 0.0,
                        "direccion": str(row['direccion']),
                        "producto": str(row['producto']),
                        "business": str(row['business']),
                        "observaciones": str(row['observaciones']) if pd.notna(row['observaciones']) else "",
                        "estado": "POR ARMAR"
                    })
                
                try:
                    supabase.table("pedidos").insert(nuevos_registros).execute()
                    for op in operaciones_descuento:
                        supabase.table("inventario").update({"stock_actual": op['nuevo_stock']}).eq("sku", op['sku']).execute()
                    
                    st.session_state['msg_exito'] = f"✅ ¡{len(nuevos_registros)} pedidos registrados en la nube!"
                    if alertas_stock:
                        st.session_state['msg_alertas'] = list(set(alertas_stock))
                    
                    descargar_datos_seguros.clear()
                    st.session_state['limpiador_tab1'] += 1 
                    st.rerun() 
                        
                except Exception as e:
                    st.error(f"❌ Error al guardar en la nube: {e}")
        else:
            st.warning("⚠️ La tabla está vacía.")

# --- PESTAÑA 2: RUTAS Y DESPACHOS ---
with tab2:
    st.header("Torre de Control de Despachos")
    
    datos_crudos_pedidos = descargar_datos_seguros("pedidos")
    
    if datos_crudos_pedidos is not None:
        df_todos = pd.DataFrame(datos_crudos_pedidos)
        
        if df_todos.empty:
            st.info("Aún no hay pedidos registrados. Usa la Pestaña 1.")
        else:
            def parse_dmy(d_str):
                try: return datetime.datetime.strptime(str(d_str), "%d/%m/%Y")
                except: return datetime.datetime.min

            fechas_validas = [d for d in df_todos['fecha_entrega'].dropna().unique() if str(d).strip() != ""]
            lista_fechas = sorted(fechas_validas, key=parse_dmy)
            hoy_str = datetime.datetime.now().strftime("%d/%m/%Y")
            
            if hoy_str not in lista_fechas:
                lista_fechas.append(hoy_str)
                lista_fechas = sorted(lista_fechas, key=parse_dmy)
                
            try: index_hoy = lista_fechas.index(hoy_str)
            except: index_hoy = len(lista_fechas) - 1
            
            fecha_filtro = st.selectbox("📅 Fecha de ruta:", options=lista_fechas, index=index_hoy)
            medios_seleccionados = st.multiselect("Courier:", options=opciones_medio, default=["MD", "ENTRE GO", "URB", "PROV"], max_selections=4)
            
            if medios_seleccionados:
                columnas = st.columns(2)
                for i, medio in enumerate(medios_seleccionados):
                    with columnas[i % 2]:
                        
                        filtro_medio = df_todos['medio'] == medio
                        filtro_fecha = (df_todos['fecha_entrega'] == fecha_filtro) | (df_todos['estado'] == "REPROGRAMADO")
                        df_medio = df_todos[filtro_medio & filtro_fecha].copy()
                        
                        if not df_medio.empty:
                            total_pedidos = len(df_medio)
                            estados_listos = ['ARMADO', 'EN RUTA', 'ENTREGADO']
                            pedidos_armados = len(df_medio[df_medio['estado'].isin(estados_listos)])
                            
                            st.markdown(f"<h3 style='margin-bottom: 5px; margin-top: 10px;'>🚚 {medio} <span style='font-size: 16px; font-weight: normal; color: #888;'>({pedidos_armados} de {total_pedidos} listos)</span></h3>", unsafe_allow_html=True)
                            
                            df_medio = df_medio.sort_values(by="id_pedido", ascending=False)
                            
                            columnas_mostrar = ['id_pedido', 'nombre', 'celular', 'distrito', 'monto', 'direccion', 'producto', 'business', 'estado']
                            df_estilo = df_medio[columnas_mostrar].style.apply(resaltar_estados, axis=1)
                            
                            df_rutas = st.data_editor(
                                df_estilo, 
                                key=f"editor_{medio}", 
                                disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "direccion", "producto", "business"], 
                                column_config={
                                    "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_general, required=True)
                                }, 
                                use_container_width=True, hide_index=True
                            )
                            
                            if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                                cambios = 0
                                auto_devueltos = 0
                                for index, row in df_rutas.iterrows():
                                    estado_anterior = df_medio.loc[index, 'estado']
                                    if row['estado'] != estado_anterior:
                                        hizo_devolucion = procesar_cambio_estado_con_stock(row['id_pedido'], estado_anterior, row['estado'], row['producto'])
                                        if hizo_devolucion: auto_devueltos += 1
                                        
                                        supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                                        cambios += 1
                                
                                if cambios > 0:
                                    mensaje = f"✅ Se actualizaron {cambios} pedidos."
                                    if auto_devueltos > 0:
                                        mensaje += f" 🔄 ¡Stock de {auto_devueltos} pedidos reingresado automáticamente!"
                                    st.success(mensaje)
                                    
                                    descargar_datos_seguros.clear() 
                                    st.rerun()
                        else:
                            st.markdown(f"<h3 style='margin-bottom: 5px;'>🚚 {medio}</h3>", unsafe_allow_html=True)
                            st.info("Ruta limpia.")

# --- PESTAÑA 3: BUSCAR Y EDITAR ---
with tab3:
    st.header("✏️ Buscador y Edición de Pedidos")
    datos_edicion = descargar_datos_seguros("pedidos")
    
    if datos_edicion is not None:
        df_editar = pd.DataFrame(datos_edicion)
        if not df_editar.empty:
            busqueda = st.text_input("🔍 Buscar pedido (puedes buscar por nombre, id o fecha):")
            if busqueda:
                df_editar = df_editar[df_editar.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
            
            df_editar.insert(0, '🗑️ Eliminar', False)
            
            st.write("Realiza modificaciones o selecciona pedidos para borrarlos del sistema:")
            df_editado_global = st.data_editor(
                df_editar.head(30), 
                use_container_width=True, hide_index=True, disabled=["id_pedido"],
                column_config={
                    "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio), 
                    "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_todas),
                    "🗑️ Eliminar": st.column_config.CheckboxColumn("🗑️ Eliminar", default=False, width="small")
                }
            )
            
            col_guardar, col_borrar = st.columns(2)
            
            with col_guardar:
                if st.button("💾 Guardar Ediciones", use_container_width=True):
                    try:
                        cambios = 0
                        auto_devueltos = 0
                        for index, row in df_editado_global.iterrows():
                            if row['🗑️ Eliminar']: continue
                            
                            estado_anterior = df_editar.loc[index, 'estado']
                            if row['estado'] != estado_anterior:
                                hizo_devolucion = procesar_cambio_estado_con_stock(row['id_pedido'], estado_anterior, row['estado'], row['producto'])
                                if hizo_devolucion: auto_devueltos += 1
                            
                            registro_actualizado = row.drop('🗑️ Eliminar').to_dict()
                            supabase.table("pedidos").update(registro_actualizado).eq("id_pedido", row['id_pedido']).execute()
                            cambios += 1
                        
                        mensaje = f"✅ {cambios} ediciones guardadas."
                        if auto_devueltos > 0:
                            mensaje += f" 🔄 Stock reingresado en anulaciones de almacén."
                        st.success(mensaje)
                        
                        descargar_datos_seguros.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error guardando: {e}")
            
            with col_borrar:
                if st.button("🗑️ Eliminar Seleccionados", use_container_width=True):
                    seleccionados = df_editado_global[df_editado_global['🗑️ Eliminar'] == True]
                    if not seleccionados.empty:
                        try:
                            eliminados = 0
                            
                            for index, row in seleccionados.iterrows():
                                supabase.table("pedidos").delete().eq("id_pedido", row['id_pedido']).execute()
                                eliminados += 1
                                
                            st.success(f"✅ ¡{eliminados} pedidos eliminados permanentemente del sistema!")
                            descargar_datos_seguros.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error eliminando pedidos: {e}")
                    else:
                        st.warning("⚠️ Primero marca la casilla '🗑️ Eliminar' en los pedidos que te equivocaste.")
        else:
            st.info("No hay pedidos para editar.")

# --- PESTAÑA 4: INVENTARIO ---
with tab4:
    st.header("📊 Maestro de Inventario y Alertas")
    datos_inv_full = descargar_datos_seguros("inventario")
    
    if datos_inv_full is not None:
        df_inv = pd.DataFrame(datos_inv_full)
        if df_inv.empty:
            df_inv = pd.DataFrame(index=range(10), columns=["nombre", "sku", "stock_actual", "precio", "stock_minimo", "stock_ideal"])
        else:
            # APLICAMOS EL ORDENAMIENTO ALFANUMÉRICO ANTES DE MOSTRAR
            df_inv['sku'] = df_inv['sku'].fillna('')
            df_inv = df_inv.sort_values(by='sku', key=lambda col: col.map(clave_orden_natural)).reset_index(drop=True)
            
        df_inv_editado = st.data_editor(
            df_inv, num_rows="dynamic",
            column_config={
                "nombre": st.column_config.TextColumn("Nombre", required=True),
                "sku": st.column_config.TextColumn("SKU", required=True),
                "stock_actual": st.column_config.NumberColumn("Stock", min_value=0, step=1, required=True),
            }, use_container_width=True, height=400
        )
        
        if st.button("💾 Guardar y Actualizar Inventario"):
            df_inv_limpio = df_inv_editado.dropna(subset=['sku', 'nombre'], how='any').copy()
            df_inv_limpio['sku'] = df_inv_limpio['sku'].astype(str).str.strip()
            if df_inv_limpio.duplicated(subset=['sku']).any():
                df_inv_limpio = df_inv_limpio.drop_duplicates(subset=['sku'], keep='last')
            
            df_inv_limpio['stock_actual'] = pd.to_numeric(df_inv_limpio['stock_actual'], errors='coerce').fillna(0).astype(int)
            df_inv_limpio['precio'] = pd.to_numeric(df_inv_limpio['precio'], errors='coerce').fillna(0.0)
            df_inv_limpio['stock_minimo'] = pd.to_numeric(df_inv_limpio['stock_minimo'], errors='coerce').fillna(0).astype(int)
            df_inv_limpio['stock_ideal'] = pd.to_numeric(df_inv_limpio['stock_ideal'], errors='coerce').fillna(0).astype(int)
            
            try:
                supabase.table("inventario").delete().neq("sku", "BORRAR_TODO").execute()
                registros_inv = df_inv_limpio.to_dict('records')
                supabase.table("inventario").insert(registros_inv).execute()
                st.success("✅ Inventario en la nube actualizado.")
                
                descargar_datos_seguros.clear() 
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar inventario: {e}")
                
        st.markdown("---")
        st.subheader("🛒 Panel de Compras (Reposición)")
        
        if not df_inv.empty and 'stock_minimo' in df_inv.columns:
            df_inv['stock_minimo'] = pd.to_numeric(df_inv['stock_minimo'], errors='coerce').fillna(0)
            df_inv['stock_ideal'] = pd.to_numeric(df_inv['stock_ideal'], errors='coerce').fillna(0)
            df_inv['stock_actual'] = pd.to_numeric(df_inv['stock_actual'], errors='coerce').fillna(0)
            
            df_real = df_inv[(df_inv['stock_minimo'] > 0) & (df_inv['stock_ideal'] > 0)].copy()
            
            if not df_real.empty:
                df_critico = df_real[df_real['stock_actual'] <= df_real['stock_minimo']].copy()
                
                if not df_critico.empty:
                    df_critico['A Comprar'] = df_critico['stock_ideal'] - df_critico['stock_actual']
                    df_critico['A Comprar'] = df_critico['A Comprar'].apply(lambda x: x if x > 0 else 0)
                    
                    st.error(f"⚠️ Tienes {len(df_critico)} productos en nivel crítico.")
                    st.dataframe(
                        df_critico[['sku', 'nombre', 'stock_actual', 'stock_minimo', 'stock_ideal', 'A Comprar']],
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.success("✅ Tu inventario principal está sano.")
            else:
                st.info("ℹ️ Define el Stock Mínimo y Stock Ideal en la tabla superior para activar las alertas de reposición.")

# --- PESTAÑA 5: SHALOM (PROVINCIAS) ---
with tab5:
    st.header("📦 Control Shalom (Envíos a Provincia)")
    
    datos_shalom = descargar_datos_seguros("pedidos")
    
    if datos_shalom is not None:
        df_shalom = pd.DataFrame(datos_shalom)
        
        if not df_shalom.empty:
            estados_finales = ["ENTREGADO", "ANULADO", "DEVOLUCION"]
            df_prov = df_shalom[(df_shalom['medio'] == 'PROV') & (~df_shalom['estado'].isin(estados_finales))].copy()
            
            if not df_prov.empty:
                df_prov['adelanto'] = 0.0
                df_prov['deuda'] = 0.0
                df_prov['clave'] = ""
                
                for idx, row in df_prov.iterrows():
                    obs = str(row['observaciones']).lower() if pd.notna(row['observaciones']) else ""
                    monto = float(row['monto']) if pd.notna(row['monto']) and str(row['monto']).strip() != "" else 0.0
                    
                    adelanto = 0.0
                    match_adelanto = re.search(r'adelanto\s*:?\s*(\d+(?:\.\d+)?)', obs)
                    if match_adelanto:
                        adelanto = float(match_adelanto.group(1))
                        
                    clave = ""
                    match_clave = re.search(r'clave\s*:?\s*(\d{4})', obs)
                    if match_clave:
                        clave = match_clave.group(1)
                    else:
                        match_4d = re.search(r'\b\d{4}\b', obs)
                        if match_4d:
                            clave = match_4d.group()
                            
                    df_prov.at[idx, 'adelanto'] = adelanto
                    df_prov.at[idx, 'deuda'] = monto - adelanto
                    df_prov.at[idx, 'clave'] = clave
                
                df_prov = df_prov.sort_values(by="id_pedido", ascending=False)
                
                st.write(f"Mostrando **{len(df_prov)}** envíos en tránsito a provincia. Los pedidos marcados como 'ENTREGADO' desaparecerán automáticamente.")
                
                columnas_shalom = ['id_pedido', 'nombre', 'celular', 'monto', 'direccion', 'adelanto', 'deuda', 'clave', 'estado']
                
                df_rutas_shalom = st.data_editor(
                    df_prov[columnas_shalom], 
                    key="editor_shalom", 
                    disabled=["id_pedido", "nombre", "celular", "monto", "direccion", "adelanto", "deuda", "clave"], 
                    column_config={
                        "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_todas, required=True),
                        "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f"),
                        "adelanto": st.column_config.NumberColumn("Adelanto", format="S/ %.2f"),
                        "deuda": st.column_config.NumberColumn("Deuda a Cobrar", format="S/ %.2f"),
                    }, 
                    use_container_width=True, hide_index=True
                )
                
                if st.button("💾 Guardar Cambios Shalom"):
                    cambios = 0
                    auto_devueltos = 0
                    for index, row in df_rutas_shalom.iterrows():
                        estado_anterior = df_prov.loc[index, 'estado']
                        if row['estado'] != estado_anterior:
                            hizo_devolucion = procesar_cambio_estado_con_stock(row['id_pedido'], estado_anterior, row['estado'], row['producto'])
                            if hizo_devolucion: auto_devueltos += 1
                            
                            supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                            cambios += 1
                    
                    if cambios > 0:
                        mensaje = f"✅ Se actualizaron {cambios} pedidos de provincia."
                        if auto_devueltos > 0:
                            mensaje += f" 🔄 ¡Stock de {auto_devueltos} pedidos anulados reingresado automáticamente!"
                        st.success(mensaje)
                        
                        descargar_datos_seguros.clear()
                        st.rerun()
            else:
                st.info("Ruta limpia. No hay envíos pendientes de cobro/recojo en provincia.")
        else:
            st.info("Aún no hay pedidos registrados.")

# --- PESTAÑA 6: INGRESO DE MERCADERÍA ---
with tab6:
    st.header("📥 Ingreso de Mercadería (Reposición y Devoluciones de Ruta)")
    st.write("Ingresa el SKU y la cantidad de la mercadería que regresa físicamente al almacén.")
    
    if 'msg_exito_ingreso' in st.session_state:
        st.success(st.session_state['msg_exito_ingreso'])
        del st.session_state['msg_exito_ingreso']

    datos_inv_repo = descargar_datos_seguros("inventario")
    if datos_inv_repo is not None:
        inventario_db = {item['sku']: item for item in datos_inv_repo}
        
        df_ingreso_base = pd.DataFrame(index=range(10), columns=["sku", "cantidad"])
        
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
            st.subheader("1. Escribe aquí:")
            df_ingreso = st.data_editor(
                df_ingreso_base,
                num_rows="dynamic",
                key=f"editor_ingreso_{st.session_state['limpiador_ingreso']}",
                column_config={
                    "sku": st.column_config.TextColumn("SKU", required=True),
                    "cantidad": st.column_config.NumberColumn("Cantidad", min_value=1, step=1)
                },
                use_container_width=True
            )
        
        df_validos = df_ingreso.dropna(subset=['sku', 'cantidad']).copy()
        
        with col2:
            st.subheader("2. Verificación Visual:")
            if not df_validos.empty:
                df_validos['sku'] = df_validos['sku'].astype(str).str.strip()
                df_validos['cantidad'] = pd.to_numeric(df_validos['cantidad'], errors='coerce').fillna(0).astype(int)
                df_validos = df_validos[df_validos['cantidad'] > 0]
                
                nombres = []
                errores_sku = []
                
                for sku in df_validos['sku']:
                    if sku in inventario_db:
                        nombres.append(inventario_db[sku]['nombre'])
                    else:
                        nombres.append("❌ NO EXISTE")
                        errores_sku.append(sku)
                
                df_validos['Producto (Autocompletado)'] = nombres
                
                st.dataframe(
                    df_validos[['sku', 'Producto (Autocompletado)', 'cantidad']], 
                    use_container_width=True, 
                    hide_index=True
                )
                
                if errores_sku:
                    st.error(f"⚠️ Corrige los SKU que no existen: {', '.join(errores_sku)}")
                else:
                    st.success("✅ Todos los SKUs son válidos. Listo para ingresar.")
                    if st.button("💾 Ingresar Mercadería y Sumar Stock", use_container_width=True):
                        try:
                            for idx, row in df_validos.iterrows():
                                sku_ingreso = row['sku']
                                cant_ingreso = row['cantidad']
                                stock_actual = inventario_db[sku_ingreso]['stock_actual']
                                nuevo_stock = stock_actual + cant_ingreso
                                
                                supabase.table("inventario").update({"stock_actual": nuevo_stock}).eq("sku", sku_ingreso).execute()
                            
                            st.session_state['msg_exito_ingreso'] = f"✅ ¡Se sumó el stock de {len(df_validos)} productos correctamente!"
                            
                            descargar_datos_seguros.clear() 
                            st.session_state['limpiador_ingreso'] += 1
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Error al sumar stock: {e}")
            else:
                st.info("Comienza a escribir a la izquierda para ver los nombres aquí.")
