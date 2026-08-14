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
if 'filas_erroneas' not in st.session_state:
    st.session_state['filas_erroneas'] = []
# --- NUEVA LÍNEA PARA EL HISTORIAL ---
if 'historial_ingresos_sesion' not in st.session_state:
    st.session_state['historial_ingresos_sesion'] = []

st.markdown("""
    <style>
    .stButton>button { background-color: #40E0D0; color: black; font-weight: bold; border-radius: 5px; border: 1px solid #000000; }
    </style>
""", unsafe_allow_html=True)

# --- 2. CONEXIÓN BÁSICA ---
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

# --- 3. NUEVO MOTOR ANTI-CUELGUES ---
@st.cache_data(show_spinner=False, ttl=180)
def cargar_todo():
    try:
        inv = supabase.table("inventario").select("*").execute().data
        ped = supabase.table("pedidos").select("*").order("id_pedido", desc=True).limit(500).execute().data
        prov = supabase.table("pedidos").select("*").eq("medio", "PROV").neq("estado", "ENTREGADO").neq("estado", "ANULADO").neq("estado", "DEVOLUCION").execute().data
        
        pedidos_consolidados = {p['id_pedido']: p for p in prov} if prov else {}
        if ped:
            for p in ped: pedidos_consolidados[p['id_pedido']] = p
            
        return inv, list(pedidos_consolidados.values())
    except Exception as e:
        return None, None

inv_global, ped_global = cargar_todo()

if inv_global is None or ped_global is None:
    st.error("⚠️ Hubo un micro-corte de internet al conectar con la base de datos.")
    if st.button("🔄 Reconectar Ahora"):
        cargar_todo.clear()
        st.rerun()
    st.stop()

# --- 4. VARIABLES GLOBALES Y FUNCIONES ---
opciones_medio = ["MD", "ENTRE GO", "SELLER", "URB", "PROV", "ENTRE GO 2", "INDRIVER", "ENTREGATE", "TIENDA Y", "TIENDA C", "TIENDA S"]
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
            try: articulos.append({'sku': sku, 'cant': int(cant_str)})
            except: articulos.append({'sku': p, 'cant': 1})
        else:
            articulos.append({'sku': p, 'cant': 1})
    return articulos

def resaltar_estados(row):
    color = ''
    if row['estado'] == 'ARMADO': color = 'background-color: #e8f5e9; color: black'
    elif row['estado'] == 'EN RUTA': color = 'background-color: #e3f2fd; color: black'
    elif row['estado'] == 'ENTREGADO': color = 'background-color: #cfd8dc; color: #546e7a'
    elif row['estado'] in ['ANULADO', 'DEVOLUCION']: color = 'background-color: #ffebee; color: black'
    elif row['estado'] == 'REPROGRAMADO': color = 'background-color: #fff3e0; color: black'
    return [color] * len(row)

def procesar_fecha(valor):
    if pd.isna(valor) or valor == "": return ""
    if hasattr(valor, 'strftime'): return valor.strftime("%Y-%m-%d")
    return str(valor).strip()

def parse_fecha(d_str):
    d_str = str(d_str).strip()
    try: return datetime.datetime.strptime(d_str, "%Y-%m-%d")
    except:
        try: return datetime.datetime.strptime(d_str, "%d/%m/%Y")
        except: return datetime.datetime.min

def procesar_cambio_estado_con_stock(id_pedido, estado_antiguo, estado_nuevo, producto_str):
    if estado_antiguo in ["POR ARMAR", "ARMADO", "REPROGRAMADO"] and estado_nuevo == "ANULADO":
        if inv_global:
            inventario_db = {item['sku']: item for item in inv_global}
            articulos = decodificar_productos(producto_str)
            for art in articulos:
                if art['sku'] in inventario_db:
                    stock_actual = inventario_db[art['sku']]['stock_actual']
                    nuevo_stock = stock_actual + art['cant']
                    supabase.table("inventario").update({"stock_actual": nuevo_stock}).eq("sku", art['sku']).execute()
        return True 
    return False

def clave_orden_natural(sku):
    return [int(texto) if texto.isdigit() else texto.lower() for texto in re.split(r'(\d+)', str(sku))]

def obtener_fecha_peru(formato="%Y-%m-%d"):
    hora_peru = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    return hora_peru.strftime(formato)

st.title("📦 Panel de Control Operativo")
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", 
    "📊 Maestro de Inventario", "📦 Shalom (Provincias)", "📥 Ingreso Mercadería", "📈 Resumen del Día"
])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    
    if 'msg_exito' in st.session_state:
        st.success(st.session_state['msg_exito'])
        del st.session_state['msg_exito']
    if 'msg_errores' in st.session_state:
        for error in st.session_state['msg_errores']: st.error(error)
        del st.session_state['msg_errores']
    if 'msg_alertas' in st.session_state:
        for alerta in st.session_state['msg_alertas']: st.warning(alerta)
        del st.session_state['msg_alertas']

    st.write("Copia de tu Excel y pega directo en la primera celda.")
    
    columnas_base = ["fecha_pedido", "fecha_entrega", "nombre", "celular", "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"]
    
    if st.session_state['filas_erroneas']:
        df_previo = pd.DataFrame(st.session_state['filas_erroneas'])[columnas_base]
        df_vacias = pd.DataFrame(index=range(10), columns=columnas_base)
        df_base = pd.concat([df_previo, df_vacias], ignore_index=True)
    else:
        df_base = pd.DataFrame(index=range(15), columns=columnas_base)
        
    # --- NUEVAS LÍNEAS PARA EVITAR EL CHOQUE DE FORMATOS ---
    df_base['fecha_pedido'] = pd.to_datetime(df_base['fecha_pedido'], errors='coerce')
    df_base['fecha_entrega'] = pd.to_datetime(df_base['fecha_entrega'], errors='coerce')
    df_base['monto'] = pd.to_numeric(df_base['monto'], errors='coerce')
    # --------------------------------------------------------
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        key=f"editor_pedidos_{st.session_state['limpiador_tab1']}",
        column_config={
            "fecha_pedido": st.column_config.DateColumn("Fecha Pedido", format="YYYY-MM-DD"),
            "fecha_entrega": st.column_config.DateColumn("Fecha Entrega", format="YYYY-MM-DD"),
            "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio),
            "monto": st.column_config.NumberColumn("Monto", format="S/ %.2f"),
            "business": st.column_config.SelectboxColumn("Business", options=opciones_business),
        },
        use_container_width=True
    )
    
    if st.button("Registrar Pedidos"):
        df_limpio = df_editado.dropna(subset=['nombre', 'producto'], how='any').copy()
        if not df_limpio.empty:
            inventario_db = {item['sku']: item for item in inv_global} if inv_global else {}
            pedidos_a_guardar = []
            pedidos_malos_df = [] 
            alertas_stock = []
            errores_registro = []
            
            for index, row in df_limpio.iterrows():
                nombre = str(row['nombre']).strip()
                medio = str(row['medio']).strip() if pd.notna(row['medio']) else ""
                business = str(row['business']).strip() if pd.notna(row['business']) else ""
                producto = str(row['producto']).strip()
                
                if medio == "" or business == "":
                    errores_registro.append(f"❌ **{nombre}**: Faltó Medio o Business.")
                    pedidos_malos_df.append(row.to_dict())
                    continue
                
                articulos_pedidos = decodificar_productos(producto)
                skus_invalidos = [art['sku'] for art in articulos_pedidos if art['sku'] not in inventario_db]
                if skus_invalidos:
                    errores_registro.append(f"❌ **{nombre}**: El SKU no existe ({', '.join(skus_invalidos)}).")
                    pedidos_malos_df.append(row.to_dict())
                    continue
                
                pedidos_a_guardar.append(row)
                for art in articulos_pedidos:
                    inventario_db[art['sku']]['stock_actual'] -= art['cant']
            
            if pedidos_a_guardar:
                ultimo_numero = 1000
                if ped_global:
                    ids = [int(p['id_pedido'].replace("CG-", "")) for p in ped_global if p['id_pedido'].startswith("CG-")]
                    if ids: ultimo_numero = max(ids)
                
                nuevos_registros = []
                for row in pedidos_a_guardar:
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
                        "direccion": str(row['direccion']) if pd.notna(row['direccion']) else "",
                        "producto": str(row['producto']),
                        "business": str(row['business']),
                        "observaciones": str(row['observaciones']) if pd.notna(row['observaciones']) else "",
                        "estado": "POR ARMAR"
                    })
                try:
                    supabase.table("pedidos").insert(nuevos_registros).execute()
                    skus_actualizados = set()
                    for row in pedidos_a_guardar:
                        for art in decodificar_productos(row['producto']):
                            skus_actualizados.add(art['sku'])
                            
                    for sku in skus_actualizados:
                        nuevo_stock = inventario_db[sku]['stock_actual']
                        stock_minimo = inventario_db[sku].get('stock_minimo', 0)
                        supabase.table("inventario").update({"stock_actual": nuevo_stock}).eq("sku", sku).execute()
                        if nuevo_stock < 0: alertas_stock.append(f"⚠️ '{sku}' stock negativo ({nuevo_stock}).")
                        elif nuevo_stock <= stock_minimo: alertas_stock.append(f"🔔 '{sku}' al límite ({nuevo_stock}).")
                            
                    st.session_state['msg_exito'] = f"✅ ¡{len(nuevos_registros)} pedidos registrados!"
                except Exception as e:
                    st.error(f"❌ Error guardando: {e}")
                    
            st.session_state['msg_errores'] = errores_registro
            st.session_state['msg_alertas'] = alertas_stock
            st.session_state['filas_erroneas'] = pedidos_malos_df 
            st.session_state['limpiador_tab1'] += 1 
            cargar_todo.clear()
            st.rerun() 
        else:
            st.warning("⚠️ Tabla vacía.")

# --- PESTAÑA 2: RUTAS ---
with tab2:
    st.header("Torre de Control de Despachos")
    if ped_global is not None:
        df_todos = pd.DataFrame(ped_global)
        if not df_todos.empty:
            fechas_validas = [d for d in df_todos['fecha_entrega'].dropna().unique() if str(d).strip() != ""]
            lista_fechas = sorted(fechas_validas, key=parse_fecha)
            hoy_str = obtener_fecha_peru()
            
            if hoy_str not in lista_fechas:
                lista_fechas.append(hoy_str)
                lista_fechas = sorted(lista_fechas, key=parse_fecha)
                
            try: index_hoy = lista_fechas.index(hoy_str)
            except: index_hoy = len(lista_fechas) - 1
            
            fecha_filtro = st.selectbox("📅 Fecha de ruta:", options=lista_fechas, index=index_hoy)
            medios_seleccionados = st.multiselect("Courier:", options=opciones_medio, default=opciones_medio)
            
            if medios_seleccionados:
                columnas = st.columns(2)
                for i, medio in enumerate(medios_seleccionados):
                    with columnas[i % 2]:
                        filtro_medio = df_todos['medio'] == medio
                        filtro_fecha = (df_todos['fecha_entrega'] == fecha_filtro) | (df_todos['estado'] == "REPROGRAMADO")
                        df_medio = df_todos[filtro_medio & filtro_fecha].copy()
                        
                        if not df_medio.empty:
                            pedidos_armados = len(df_medio[df_medio['estado'].isin(['ARMADO', 'EN RUTA', 'ENTREGADO'])])
                            st.markdown(f"### 🚚 {medio} ({pedidos_armados}/{len(df_medio)} listos)")
                            df_medio = df_medio.sort_values(by="id_pedido", ascending=False)
                            
                            df_estilo = df_medio[['id_pedido', 'estado', 'nombre', 'celular', 'distrito', 'monto', 'direccion', 'producto', 'business']].style.apply(resaltar_estados, axis=1)
                            
                            altura_dinamica = min(500, (len(df_medio) * 35) + 40)
                            
                            df_rutas = st.data_editor(df_estilo, key=f"ed_{medio}", height=altura_dinamica, disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "direccion", "producto", "business"], column_config={"id_pedido": None, "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_general)}, use_container_width=True, hide_index=True)
                            if st.button(f"Guardar - {medio}", key=f"btn_{medio}"):
                                for index, row in df_rutas.iterrows():
                                    est_ant = df_medio.loc[index, 'estado']
                                    if row['estado'] != est_ant:
                                        procesar_cambio_estado_con_stock(row['id_pedido'], est_ant, row['estado'], row['producto'])
                                        supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                                st.success("✅ Guardado.")
                                cargar_todo.clear()
                                st.rerun()
                        else:
                            st.markdown(f"### 🚚 {medio}")
                            st.info("Ruta limpia.")
        else:
            st.info("Aún no hay pedidos registrados.")

# --- PESTAÑA 3: EDITAR ---
with tab3:
    st.header("✏️ Editar Pedidos")
    if ped_global is not None:
        df_editar = pd.DataFrame(ped_global)
        if not df_editar.empty:
            busqueda = st.text_input("🔍 Buscar pedido:")
            if busqueda: df_editar = df_editar[df_editar.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
            df_editar.insert(0, '🗑️ Eliminar', False)
            
            df_edi = st.data_editor(df_editar.head(30), use_container_width=True, hide_index=True, disabled=["id_pedido"], column_config={"medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio), "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_todas), "🗑️ Eliminar": st.column_config.CheckboxColumn("Eliminar", default=False)})
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("💾 Guardar Ediciones", use_container_width=True):
                    for index, row in df_edi.iterrows():
                        if row['🗑️ Eliminar']: continue
                        est_ant = df_editar.loc[index, 'estado']
                        if row['estado'] != est_ant: procesar_cambio_estado_con_stock(row['id_pedido'], est_ant, row['estado'], row['producto'])
                        reg = row.drop('🗑️ Eliminar').to_dict()
                        supabase.table("pedidos").update(reg).eq("id_pedido", row['id_pedido']).execute()
                    st.success("✅ Guardado.")
                    cargar_todo.clear()
                    st.rerun()
            with c2:
                if st.button("🗑️ Eliminar Seleccionados", use_container_width=True):
                    sel = df_edi[df_edi['🗑️ Eliminar'] == True]
                    for index, row in sel.iterrows(): supabase.table("pedidos").delete().eq("id_pedido", row['id_pedido']).execute()
                    st.success("✅ Eliminados.")
                    cargar_todo.clear()
                    st.rerun()
        else:
            st.info("No hay pedidos para editar.")

# --- PESTAÑA 4: INVENTARIO ---
with tab4:
    st.header("📊 Inventario")
    if inv_global is not None:
        df_inv = pd.DataFrame(inv_global)
        if df_inv.empty:
            df_inv = pd.DataFrame(index=range(10), columns=["nombre", "sku", "stock_actual", "precio", "stock_minimo", "stock_ideal"])
        else:
            df_inv = df_inv.fillna('')
            df_inv = df_inv.sort_values(by='sku', key=lambda col: col.map(clave_orden_natural)).reset_index(drop=True)
            
        df_ie = st.data_editor(df_inv, num_rows="dynamic", use_container_width=True, height=400)
        
        if st.button("💾 Guardar Inventario"):
            df_il = df_ie.dropna(subset=['sku', 'nombre'], how='any').copy()
            if not df_il.empty:
                df_il['sku'] = df_il['sku'].astype(str).str.strip()
                df_il = df_il.drop_duplicates(subset=['sku'], keep='last')
                df_il['stock_actual'] = pd.to_numeric(df_il['stock_actual'], errors='coerce').fillna(0).astype(int)
                
                if 'precio' in df_il.columns: df_il['precio'] = pd.to_numeric(df_il['precio'], errors='coerce').fillna(0.0)
                if 'stock_minimo' in df_il.columns: df_il['stock_minimo'] = pd.to_numeric(df_il['stock_minimo'], errors='coerce').fillna(0).astype(int)
                if 'stock_ideal' in df_il.columns: df_il['stock_ideal'] = pd.to_numeric(df_il['stock_ideal'], errors='coerce').fillna(0).astype(int)
                
                try:
                    supabase.table("inventario").delete().neq("sku", "BORRAR_TODO").execute()
                    supabase.table("inventario").insert(df_il.to_dict('records')).execute()
                    st.success("✅ Actualizado.")
                    cargar_todo.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error guardando inventario: {e}")
            else:
                st.warning("⚠️ No hay datos válidos para guardar.")
        # --- NUEVO CUADRO DE REPOSICIÓN ---
        st.divider()
        st.subheader("🛒 Alertas de Reposición")
        
        if not df_inv.empty:
            # Aseguramos que los números se lean correctamente
            df_inv['stock_actual'] = pd.to_numeric(df_inv['stock_actual'], errors='coerce').fillna(0)
            if 'stock_minimo' in df_inv.columns:
                df_inv['stock_minimo'] = pd.to_numeric(df_inv['stock_minimo'], errors='coerce').fillna(0)
                
                # Filtramos los que están en rojo
                df_reposicion = df_inv[df_inv['stock_actual'] <= df_inv['stock_minimo']].copy()
                
                if not df_reposicion.empty:
                    # Calculamos cuánto falta para llegar al ideal
                    if 'stock_ideal' in df_reposicion.columns:
                        df_reposicion['stock_ideal'] = pd.to_numeric(df_reposicion['stock_ideal'], errors='coerce').fillna(0)
                        df_reposicion['Faltante a Comprar'] = df_reposicion['stock_ideal'] - df_reposicion['stock_actual']
                        # Si el cálculo da negativo, lo dejamos en 0
                        df_reposicion['Faltante a Comprar'] = df_reposicion['Faltante a Comprar'].apply(lambda x: int(x) if x > 0 else 0)
                        columnas_mostrar = ['sku', 'nombre', 'stock_actual', 'stock_minimo', 'Faltante a Comprar']
                    else:
                        columnas_mostrar = ['sku', 'nombre', 'stock_actual', 'stock_minimo']
                    
                    st.warning(f"⚠️ Tienes {len(df_reposicion)} productos con stock bajo o agotado.")
                    st.dataframe(df_reposicion[columnas_mostrar].style.apply(lambda x: ['background-color: #ffebee'] * len(x), axis=1), use_container_width=True, hide_index=True)
                else:
                    st.success("✅ Todo tu inventario está por encima del nivel mínimo. ¡No hay urgencias de compra!")

# --- PESTAÑA 5: SHALOM ---
with tab5:
    st.header("📦 Control Shalom")
    if ped_global is not None:
        df_prov = pd.DataFrame(ped_global)
        if not df_prov.empty:
            df_prov = df_prov[(df_prov['medio'] == 'PROV') & (~df_prov['estado'].isin(["ENTREGADO", "ANULADO", "DEVOLUCION"]))].copy()
            
            if not df_prov.empty:
                df_prov['adelanto'], df_prov['deuda'], df_prov['clave'] = 0.0, 0.0, ""
                for idx, row in df_prov.iterrows():
                    obs = str(row['observaciones']).lower()
                    m = float(row['monto']) if pd.notna(row['monto']) and str(row['monto']).strip() != "" else 0.0
                    ad = float(re.search(r'adelanto\s*:?\s*(\d+(?:\.\d+)?)', obs).group(1)) if re.search(r'adelanto\s*:?\s*(\d+(?:\.\d+)?)', obs) else 0.0
                    cl = re.search(r'clave\s*:?\s*(\d{4})', obs).group(1) if re.search(r'clave\s*:?\s*(\d{4})', obs) else (re.search(r'\b\d{4}\b', obs).group() if re.search(r'\b\d{4}\b', obs) else "")
                    df_prov.at[idx, 'adelanto'], df_prov.at[idx, 'deuda'], df_prov.at[idx, 'clave'] = ad, m - ad, cl
                
                df_ps = st.data_editor(df_prov[['id_pedido', 'nombre', 'celular', 'monto', 'direccion', 'adelanto', 'deuda', 'clave', 'estado']], disabled=["id_pedido", "nombre", "celular", "monto", "direccion", "adelanto", "deuda", "clave"], column_config={"estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_todas)}, use_container_width=True, hide_index=True)
                if st.button("💾 Guardar Shalom"):
                    for index, row in df_ps.iterrows():
                        est_ant = df_prov.loc[index, 'estado']
                        if row['estado'] != est_ant:
                            procesar_cambio_estado_con_stock(row['id_pedido'], est_ant, row['estado'], df_prov.loc[index, 'producto'])
                            supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                    st.success("✅ Guardado.")
                    cargar_todo.clear()
                    st.rerun()
            else: st.info("Ruta limpia. No hay envíos pendientes.")
        else:
            st.info("No hay pedidos registrados.")

# --- PESTAÑA 6: INGRESO ---
with tab6:
    st.header("📥 Ingreso de Mercadería")
    if inv_global is not None:
        inv_db = {item['sku']: item for item in inv_global} if inv_global else {}
        c1, c2 = st.columns([1, 1.5])
        
        with c1: 
            # AQUI ESTÁ LA MAGIA DEL BORRADO: La llave dinámica (key)
            df_in = st.data_editor(
                pd.DataFrame(index=range(10), columns=["sku", "cantidad"]), 
                num_rows="dynamic", 
                use_container_width=True,
                key=f"editor_ingresos_{st.session_state['limpiador_ingreso']}"
            )
            
        df_v = df_in.dropna(subset=['sku', 'cantidad']).copy()
        
        with c2:
            if not df_v.empty:
                df_v['sku'] = df_v['sku'].astype(str).str.strip()
                df_v['cantidad'] = pd.to_numeric(df_v['cantidad'], errors='coerce').fillna(0).astype(int)
                df_v = df_v[df_v['cantidad'] > 0]
                nombres = [inv_db[s]['nombre'] if s in inv_db else "❌ NO EXISTE" for s in df_v['sku']]
                df_v['Producto'] = nombres
                st.dataframe(df_v[['sku', 'Producto', 'cantidad']], use_container_width=True, hide_index=True)
                
                if "❌ NO EXISTE" not in nombres and st.button("💾 Ingresar Stock", use_container_width=True):
                    try:
                        ingresos_exitosos = []
                        hora_actual = obtener_fecha_peru("%Y-%m-%d %H:%M:%S")
                        
                        for idx, row in df_v.iterrows(): 
                            # Sumar a la base de datos
                            supabase.table("inventario").update({"stock_actual": inv_db[row['sku']]['stock_actual'] + row['cantidad']}).eq("sku", row['sku']).execute()
                            
                            # Registrar en el historial
                            ingresos_exitosos.append({
                                "Hora del Ingreso": hora_actual,
                                "SKU": row['sku'],
                                "Producto": row['Producto'],
                                "Cant. Ingresada": row['cantidad']
                            })
                        
                        # Guardar el registro en la memoria temporal
                        st.session_state['historial_ingresos_sesion'].extend(ingresos_exitosos)
                        
                        st.success("✅ Stock sumado exitosamente.")
                        
                        # INCREMENTAR LA LLAVE PARA BORRAR LA TABLA
                        st.session_state['limpiador_ingreso'] += 1
                        
                        cargar_todo.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error sumando stock: {e}")
                        
        # --- NUEVO CUADRO DE HISTORIAL ---
        st.divider()
        st.subheader("📋 Historial de Ingresos Realizados (Revisión)")
        
        if st.session_state['historial_ingresos_sesion']:
            df_historial = pd.DataFrame(st.session_state['historial_ingresos_sesion'])
            # Mostramos el historial invertido para que los últimos ingresos salgan arriba del todo
            st.dataframe(df_historial.iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("Aún no has registrado ingresos de mercadería el día de hoy.")

# --- PESTAÑA 7: RESUMEN ---
with tab7:
    st.header("📈 Resumen del Día")
    if ped_global is not None and inv_global is not None:
        hoy_str = obtener_fecha_peru()
        st.markdown(f"### 📅 Fecha: **{hoy_str}**")
        if st.button("🔄 Actualizar"):
            cargar_todo.clear()
            st.rerun()
        
        df_hoy = pd.DataFrame(ped_global)
        if not df_hoy.empty:
            df_hoy = df_hoy[(df_hoy['fecha_pedido'] == hoy_str) & (~df_hoy['estado'].isin(["ANULADO", "DEVOLUCION"]))]
            st.metric("📦 Pedidos Efectivos Hoy", len(df_hoy))
            
            if not df_hoy.empty:
                v_skus = {}
                for p in df_hoy['producto']:
                    for a in decodificar_productos(p): v_skus[a['sku']] = v_skus.get(a['sku'], 0) + a['cant']
                
                if v_skus:
                    inv_dict = {i['sku']: i for i in inv_global} if inv_global else {}
                    rep = [{"SKU": s, "Producto": inv_dict.get(s, {}).get('nombre', '⚠️ NO ENCONTRADO'), "Inicial": inv_dict.get(s, {}).get('stock_actual', 0) + c, "Vendidas": c, "Final": inv_dict.get(s, {}).get('stock_actual', 0)} for s, c in v_skus.items()]
                    st.dataframe(pd.DataFrame(rep).sort_values("Vendidas", ascending=False).reset_index(drop=True), use_container_width=True)
        else:
            st.info("No hay pedidos para resumir.")
