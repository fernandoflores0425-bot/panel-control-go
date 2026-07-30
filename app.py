import streamlit as st
import pandas as pd
import datetime
from supabase import create_client, Client

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

# Conexión segura a Supabase usando los secretos de Streamlit
@st.cache_resource
def init_connection() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_connection()

opciones_medio = ["MD", "FERRA", "SELLER", "PROV", "ENTRE GO", "INDRIVER", "TIENDA S", "TIENDA C", "TIENDA Y", "URB", "GOATE"]
opciones_business = ["MELI", "BELA", "WGO", "MGO", "VIA", "MELI2", "VEA"]
opciones_estado = ["POR ARMAR", "ARMADO", "ENTREGADO", "ANULADO", "DEVOLUCION", "REAGENDADO"]

# Función para traducir el texto "1 SKU1 + 3 SKU2"
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

st.title("📦 Panel de Control Operativo")

tab1, tab2, tab3, tab4 = st.tabs(["📝 Agendar Pedidos", "🚚 Rutas por Día", "✏️ Editar Pedidos", "📊 Maestro de Inventario"])

# --- PESTAÑA 1: AGENDAR ---
with tab1:
    st.header("Ingreso de ventas")
    st.write("Copia de tu Excel y pega directo en la primera celda. Los IDs se generarán automáticamente en la nube.")
    
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
            
            # Obtener inventario actual de Supabase
            response_inv = supabase.table("inventario").select("*").execute()
            inventario_db = {item['sku']: item for item in response_inv.data}
            
            for index, row in df_limpio.iterrows():
                articulos_pedidos = decodificar_productos(row['producto'])
                for art in articulos_pedidos:
                    if art['sku'] not in inventario_db:
                        st.error(f"❌ ERROR: El producto '{art['sku']}' (Pedido de {row['nombre']}) NO existe en el Inventario Maestro.")
                        error_bloqueante = True
                        break
                    else:
                        item_inv = inventario_db[art['sku']]
                        stock_actual = item_inv['stock_actual']
                        stock_minimo = item_inv['stock_minimo']
                        nuevo_stock = stock_actual - art['cant']
                        
                        operaciones_descuento.append({'sku': art['sku'], 'nuevo_stock': nuevo_stock})
                        
                        if nuevo_stock < 0:
                            alertas_stock.append(f"⚠️ Atención: '{art['sku']}' quedó con stock negativo ({nuevo_stock}).")
                        elif nuevo_stock <= stock_minimo:
                            alertas_stock.append(f"🔔 Alerta: '{art['sku']}' llegó a su Stock Mínimo. Quedan {nuevo_stock} unidades.")
            
            if not error_bloqueante:
                # Obtener último ID de pedido registrado para autoincrementar
                response_pedidos = supabase.table("pedidos").select("id_pedido").order("id_pedido", desc=True).limit(1).execute()
                ultimo_id = response_pedidos.data
                
                if ultimo_id and ultimo_id[0]['id_pedido'].startswith("CG-"):
                    try:
                        ultimo_numero = int(ultimo_id[0]['id_pedido'].split("-")[1])
                    except ValueError:
                        ultimo_numero = 1000
                else:
                    ultimo_numero = 1000
                
                nuevos_registros = []
                for _, row in df_limpio.iterrows():
                    ultimo_numero += 1
                    nuevo_id = f"CG-{ultimo_numero}"
                    
                    registro = {
                        "id_pedido": nuevo_id,
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
                    }
                    nuevos_registros.append(registro)
                
                # Insertar pedidos en Supabase
                supabase.table("pedidos").insert(nuevos_registros).execute()
                
                # Actualizar stock en Supabase
                for op in operaciones_descuento:
                    supabase.table("inventario").update({"stock_actual": op['nuevo_stock']}).eq("sku", op['sku']).execute()
                
                st.success(f"✅ ¡{len(nuevos_registros)} pedidos registrados con éxito en la nube!")
                for alerta in set(alertas_stock):
                    st.warning(alerta)
        else:
            st.warning("⚠️ La tabla está vacía.")

# --- PESTAÑA 2: RUTAS Y DESPACHOS ---
with tab2:
    st.header("Torre de Control de Despachos")
    
    # REPARACIÓN 1: Reemplazo de .not_.in_ por .neq() encadenados
    response_fechas = supabase.table("pedidos").select("fecha_entrega").neq("estado", "ENTREGADO").neq("estado", "ANULADO").neq("estado", "DEVOLUCION").execute()
    lista_fechas = sorted(list(set([str(item['fecha_entrega']) for item in response_fechas.data if item['fecha_entrega'] and item['fecha_entrega'] != "None"])))
    
    if not lista_fechas:
        lista_fechas = [datetime.datetime.now().strftime("%d/%m/%Y")]
        st.info("No se detectaron fechas agendadas pendientes.")
        
    fecha_filtro = st.selectbox("📅 Selecciona la fecha de ruta a procesar:", options=lista_fechas)
    medios_seleccionados = st.multiselect("Courier:", options=opciones_medio, default=["MD", "ENTRE GO", "URB", "PROV"], max_selections=4)
    
    if medios_seleccionados:
        columnas = st.columns(2)
        for i, medio in enumerate(medios_seleccionados):
            with columnas[i % 2]:
                st.subheader(f"🚚 {medio}")
                
                # REPARACIÓN 2: Reemplazo de .not_.in_ por .neq() encadenados
                response_medios = supabase.table("pedidos").select("id_pedido, nombre, celular, distrito, monto, producto, business, estado").eq("medio", medio).or_(f"fecha_entrega.eq.{fecha_filtro},estado.eq.REAGENDADO").neq("estado", "ENTREGADO").neq("estado", "ANULADO").neq("estado", "DEVOLUCION").execute()
                df_medio = pd.DataFrame(response_medios.data)
                
                if not df_medio.empty:
                    df_rutas = st.data_editor(
                        df_medio, 
                        key=f"editor_{medio}", 
                        disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "producto", "business"], 
                        column_config={"estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado, required=True)}, 
                        use_container_width=True, 
                        hide_index=True
                    )
                    if st.button(f"Guardar Cambios - {medio}", key=f"btn_{medio}"):
                        cambios = 0
                        for index, row in df_rutas.iterrows():
                            if row['estado'] != df_medio.loc[index, 'estado']:
                                supabase.table("pedidos").update({"estado": row['estado']}).eq("id_pedido", row['id_pedido']).execute()
                                cambios += 1
                        if cambios > 0:
                            st.success(f"✅ Se actualizaron {cambios} estados.")
                            st.rerun()
                else:
                    st.info("Ruta limpia.")
                    
# --- PESTAÑA 3: BUSCAR Y EDITAR ---
with tab3:
    st.header("✏️ Buscador y Edición de Pedidos")
    busqueda = st.text_input("🔍 Buscar pedido (por ID, Nombre o Celular):")
    
    if busqueda:
        response_busqueda = supabase.table("pedidos").select("*").or_(f"id_pedido.ilike.%{busqueda}%,nombre.ilike.%{busqueda}%,celular.ilike.%{busqueda}%").limit(20).execute()
    else:
        response_busqueda = supabase.table("pedidos").select("*").order("id_pedido", desc=True).limit(20).execute()
        
    df_editar = pd.DataFrame(response_busqueda.data)
    
    if not df_editar.empty:
        df_editado_global = st.data_editor(
            df_editar, 
            key="editor_global", 
            use_container_width=True, 
            hide_index=True, 
            disabled=["id_pedido"], 
            column_config={
                "medio": st.column_config.SelectboxColumn("Medio", options=opciones_medio), 
                "business": st.column_config.SelectboxColumn("Business", options=opciones_business), 
                "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado)
            }
        )
        if st.button("💾 Guardar Ediciones"):
            for _, row in df_editado_global.iterrows():
                supabase.table("pedidos").update({
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
                    "estado": str(row['estado'])
                }).eq("id_pedido", row['id_pedido']).execute()
            st.success("✅ Cambios guardados correctamente.")
            st.rerun()
    else:
        st.info("No se encontraron pedidos.")

# --- PESTAÑA 4: INVENTARIO (MAESTRO Y REPOSICIÓN) ---
with tab4:
    st.header("📊 Maestro de Inventario y Alertas")
    st.write("Gestiona tu inventario en la nube y revisa el panel de reposición.")
    
    response_inv_full = supabase.table("inventario").select("*").execute()
    df_inv = pd.DataFrame(response_inv_full.data)
    
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
        df_inv_limpio['sku'] = df_inv_limpio['sku'].astype(str).str.strip()
        
        if df_inv_limpio.duplicated(subset=['sku']).any():
            st.warning("⚠️ SKUs duplicados unificados automáticamente.")
            df_inv_limpio = df_inv_limpio.drop_duplicates(subset=['sku'], keep='last')

        df_inv_limpio['stock_actual'] = pd.to_numeric(df_inv_limpio['stock_actual'], errors='coerce').fillna(0).astype(int)
        df_inv_limpio['stock_minimo'] = pd.to_numeric(df_inv_limpio['stock_minimo'], errors='coerce').fillna(0).astype(int)
        df_inv_limpio['stock_ideal'] = pd.to_numeric(df_inv_limpio['stock_ideal'], errors='coerce').fillna(0).astype(int)
        df_inv_limpio['precio'] = pd.to_numeric(df_inv_limpio['precio'], errors='coerce').fillna(0.0)
        
        try:
            # Reemplazar tabla completa en Supabase de forma limpia
            supabase.table("inventario").delete().neq("sku", "BORRAR_TODO").execute()
            
            registros_inv = []
            for _, row in df_inv_limpio.iterrows():
                registros_inv.append({
                    "sku": str(row['sku']),
                    "nombre": str(row['nombre']),
                    "stock_actual": int(row['stock_actual']),
                    "precio": float(row['precio']),
                    "stock_minimo": int(row['stock_minimo']),
                    "stock_ideal": int(row['stock_ideal'])
                })
            supabase.table("inventario").insert(registros_inv).execute()
            st.success("✅ Maestro de inventario actualizado en la nube.")
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
                
                st.error(f"⚠️ Tienes {len(df_critico)} productos oficiales en nivel crítico.")
                st.dataframe(
                    df_critico[['sku', 'nombre', 'stock_actual', 'stock_minimo', 'stock_ideal', 'A Comprar']],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.success("✅ Tu inventario principal está sano.")
        else:
            st.info("ℹ️ Define el Stock Mínimo y Stock Ideal en la tabla superior para activar las alertas.")
