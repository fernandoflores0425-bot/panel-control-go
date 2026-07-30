import streamlit as st
import pandas as pd
import datetime
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN VISUAL ---
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

# --- 2. CONEXIÓN BLINDADA A LA NUBE ---
@st.cache_resource
def init_connection():
    try:
        # El .strip() elimina espacios en blanco accidentales al copiar/pegar
        url = st.secrets["SUPABASE_URL"].strip()
        key = st.secrets["SUPABASE_KEY"].strip()
        return create_client(url, key)
    except Exception as e:
        st.error(f"❌ Error en las credenciales (Secrets). Revisa que estén bien escritas. Detalle: {e}")
        st.stop()

supabase = init_connection()

# --- 3. VARIABLES GLOBALES ---
opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB", "GOATE"]
opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]
opciones_estado = ["POR ARMAR", "ARMADO", "ENTREGADO", "ANULADO", "DEVOLUCION", "REAGENDADO"]

# Función extractora de productos
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

# Función Anti-Crash para descargar datos
def descargar_datos_seguros(nombre_tabla):
    try:
        respuesta = supabase.table(nombre_tabla).select("*").execute()
        return respuesta.data
    except Exception as e:
        st.error(f"❌ ERROR CRÍTICO: No se pudo leer la tabla '{nombre_tabla}'. ¿Estás seguro de que la creaste en Supabase SQL Editor? Detalle técnico: {e}")
        return None

st.title("📦 Panel de Control Operativo")
tab1, tab2, tab3, tab4 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", "📊 Maestro de Inventario"])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Copia de tu Excel y pega directo en la primera celda.")
    
    df_base = pd.DataFrame(index=range(15), columns=[
        "fecha_pedido", "fecha_entrega", "nombre", "celular", 
        "distrito", "medio", "monto", "direccion", "producto", "business", "observaciones"
    ])
    
    df_editado = st.data_editor(
        df_base, 
        num_rows="dynamic",
        column_config={
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
            alertas_stock = []
            operaciones_descuento = []
            
            for index, row in df_limpio.iterrows():
                articulos_pedidos = decodificar_productos(row['producto'])
                for art in articulos_pedidos:
                    if art['sku'] not in inventario_db:
                        st.error(f"❌ ERROR: El producto '{art['sku']}' NO existe en el Inventario.")
                        error_bloqueante = True
                        break
                    else:
                        item_inv = inventario_db[art['sku']]
                        nuevo_stock = item_inv['stock_actual'] - art['cant']
                        operaciones_descuento.append({'sku': art['sku'], 'nuevo_stock': nuevo_stock})
            
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
                        "fecha_pedido": str(row['fecha_pedido']),
                        "fecha_entrega": str(row['fecha_entrega']),
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
                    st.success(f"✅ ¡{len(nuevos_registros)} pedidos registrados en la nube!")
                except Exception as e:
                    st.error(f"❌ Error al guardar en la nube: {e}")
        else:
            st.warning("⚠️ La tabla está vacía.")

# --- PESTAÑA 2: RUTAS Y DESPACHOS ---
with tab2:
    st.header("Torre de Control de Despachos")
    
    # Intento seguro de descarga
    datos_crudos_pedidos = descargar_datos_seguros("pedidos")
    
    if datos_crudos_pedidos is not None:
        df_todos = pd.DataFrame(datos_crudos_pedidos)
        
        if df_todos.empty:
            st.info("Aún no hay pedidos registrados. Usa la Pestaña 1.")
        else:
            estados_activos = ["POR ARMAR", "ARMADO", "REAGENDADO"]
            df_activos = df_todos[df_todos['estado'].isin(estados_activos)].copy()
            lista_fechas = sorted(df_activos['fecha_entrega'].dropna().unique().tolist())
            
            if not lista_fechas:
                lista_fechas = [datetime.datetime.now().strftime("%d/%m/%Y")]
                
            fecha_filtro = st.selectbox("📅 Fecha de ruta:", options=lista_fechas)
            medios_seleccionados = st.multiselect("Courier:", options=opciones_medio, default=["MD", "ENTRE GO", "URB", "PROV"], max_selections=4)
            
            if medios_seleccionados:
                columnas = st.columns(2)
                for i, medio in enumerate(medios_seleccionados):
                    with columnas[i % 2]:
                        st.subheader(f"🚚 {medio}")
                        filtro_medio = df_activos['medio'] == medio
                        filtro_fecha = (df_activos['fecha_entrega'] == fecha_filtro) | (df_activos['estado'] == "REAGENDADO")
                        
                        df_medio = df_activos[filtro_medio & filtro_fecha].copy()
                        
                        if not df_medio.empty:
                            df_rutas = st.data_editor(
                                df_medio[['id_pedido', 'nombre', 'celular', 'distrito', 'monto', 'producto', 'business', 'estado']], 
                                key=f"editor_{medio}", 
                                disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "producto", "business"], 
                                column_config={"estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado, required=True)}, 
                                use_container_width=True, hide_index=True
                            )
                            if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                                for index, row in df_rutas.iterrows():
                                    if row['estado'] != df_medio.loc[index, 'estado']:
                                        supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                                st.success("✅ Actualizado.")
                                st.rerun()
                        else:
                            st.info("Ruta limpia.")

# --- PESTAÑA 3: BUSCAR Y EDITAR ---
with tab3:
    st.header("✏️ Buscador y Edición de Pedidos")
    datos_edicion = descargar_datos_seguros("pedidos")
    
    if datos_edicion is not None:
        df_editar = pd.DataFrame(datos_edicion)
        if not df_editar.empty:
            busqueda = st.text_input("🔍 Buscar pedido:")
            if busqueda:
                df_editar = df_editar[df_editar.astype(str).apply(lambda x: x.str.contains(busqueda, case=False)).any(axis=1)]
            
            df_editado_global = st.data_editor(
                df_editar.head(20), 
                use_container_width=True, hide_index=True, disabled=["id_pedido"],
                column_config={"medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio), "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado)}
            )
            if st.button("💾 Guardar Ediciones"):
                try:
                    for _, row in df_editado_global.iterrows():
                        registro_actualizado = row.to_dict()
                        supabase.table("pedidos").update(registro_actualizado).eq("id_pedido", row['id_pedido']).execute()
                    st.success("✅ Cambios guardados.")
                except Exception as e:
                    st.error(f"❌ Error guardando: {e}")
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
            
            df_inv_limpio = df_inv_limpio.fillna(0)
            
            try:
                supabase.table("inventario").delete().neq("sku", "BORRAR_TODO").execute()
                registros_inv = df_inv_limpio.to_dict('records')
                supabase.table("inventario").insert(registros_inv).execute()
                st.success("✅ Inventario en la nube actualizado.")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Error al guardar inventario: {e}")
