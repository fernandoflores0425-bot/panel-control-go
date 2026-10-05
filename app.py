import streamlit as st
import pandas as pd
import datetime
import re
from supabase import create_client, Client

# --- 1. CONFIGURACIÓN VISUAL Y DE MEMORIA ---
st.set_page_config(page_title="Control Go - Operaciones", page_icon="logo.png", layout="wide")
if 'limpiador_tab1' not in st.session_state:
    st.session_state['limpiador_tab1'] = 0
if 'limpiador_ingreso' not in st.session_state:
    st.session_state['limpiador_ingreso'] = 0
if 'filas_erroneas' not in st.session_state:
    st.session_state['filas_erroneas'] = []
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
opciones_medio = ["MD", "ENTRE GO", "GSG", "SELLER", "URB", "PROV", "ENTRE GO 2", "INDRIVER", "ENTREGATE", "TIENDA Y", "TIENDA C", "TIENDA S"]
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

# NUEVO ESCUDO: Si el pedido decía "almacén", no devuelve el stock al anularse
def procesar_cambio_estado_con_stock(id_pedido, estado_antiguo, estado_nuevo, producto_str, observaciones_str=""):
    obs_baja = str(observaciones_str).lower()
    if "almacen" in obs_baja or "almacén" in obs_baja:
        return False # No devolvemos nada porque nunca se restó

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

def clave_orden_natural(sku):
    return [int(texto) if texto.isdigit() else texto.lower() for texto in re.split(r'(\d+)', str(sku))]

def obtener_fecha_peru(formato="%Y-%m-%d"):
    hora_peru = datetime.datetime.utcnow() - datetime.timedelta(hours=5)
    return hora_peru.strftime(formato)

# --- NUEVO TÍTULO CON LOGO ---
col_logo, col_tit = st.columns([1, 15]) 
with col_logo:
    try:
        st.image("logo.png", width=60) 
    except:
        st.write("📦") 
with col_tit:
    st.title("Panel de Control Go")

# ¡AQUÍ ESTÁ EL TRUCO! Intercambiamos el orden visual de tab2 y tab1 para que Rutas abra primero.
tab2, tab1, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🚚 Rutas por Día", "📝 Agendar Pedidos", "✏️ Editar Pedidos", 
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
        
    df_base['fecha_pedido'] = pd.to_datetime(df_base['fecha_pedido'], errors='coerce')
    df_base['fecha_entrega'] = pd.to_datetime(df_base['fecha_entrega'], errors='coerce')
    df_base['monto'] = pd.to_numeric(df_base['monto'], errors='coerce')
    
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
                observaciones = str(row['observaciones']).strip()
                
                if medio == "" or business == "":
                    errores_registro.append(f"❌ **{nombre}**: Faltó Medio o Business.")
                    pedidos_malos_df.append(row.to_dict())
                    continue
                
                if medio == "SELLER" and business != "BELA":
                    errores_registro.append(f"❌ **{nombre}**: El medio 'SELLER' solo se puede usar con el negocio 'BELA'. Corrige la celda.")
                    pedidos_malos_df.append(row.to_dict())
                    continue
                
                articulos_pedidos = decodificar_productos(producto)
                skus_invalidos = [art['sku'] for art in articulos_pedidos if art['sku'] not in inventario_db]
                if skus_invalidos:
                    errores_registro.append(f"❌ **{nombre}**: El SKU no existe ({', '.join(skus_invalidos)}).")
                    pedidos_malos_df.append(row.to_dict())
                    continue
                
                pedidos_a_guardar.append(row)
                
                # --- AQUÍ ESTÁ EL DESCUENTO CONDICIONAL ---
                obs_minusculas = observaciones.lower()
                if "almacen" not in obs_minusculas and "almacén" not in obs_minusculas:
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
                    
                    # Solo actualizamos la base de datos si el pedido NO dice almacén
                    for row in pedidos_a_guardar:
                        obs_minusculas = str(row['observaciones']).lower()
                        if "almacen" not in obs_minusculas and "almacén" not in obs_minusculas:
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
                            
                            df_rutas = st.data_editor(
                                df_estilo, 
                                key=f"ed_{medio}", 
                                height=altura_dinamica, 
                                disabled=["id_pedido", "nombre", "celular", "distrito", "monto", "direccion", "producto", "business"], 
                                column_config={
                                    "id_pedido": None, 
                                    "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_general),
                                    "monto": st.column_config.NumberColumn("Monto", format="%.2f")
                                }, 
                                use_container_width=True, 
                                hide_index=True
                            )
                            
                            if st.button(f"Guardar - {medio}", key=f"btn_{medio}"):
                                for index, row in df_rutas.iterrows():
                                    est_ant = df_medio.loc[index, 'estado']
                                    obs_str = df_medio.loc[index, 'observaciones']
                                    if row['estado'] != est_ant:
                                        procesar_cambio_estado_con_stock(row['id_pedido'], est_ant, row['estado'], row['producto'], obs_str)
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

    # =========================================================
    # FUNCIONES
    # =========================================================

    def afecta_stock(estado, obs):
        obs = str(obs).lower()
        return (
            estado != "ANULADO"
            and "almacen" not in obs
            and "almacén" not in obs
        )

    def productos_dict(texto):
        r = {}
        for p in decodificar_productos(texto):
            r[p["sku"]] = r.get(p["sku"], 0) + p["cant"]
        return r

    def ajuste_stock(prod_ant, est_ant, obs_ant,
                     prod_nuevo, est_nuevo, obs_nuevo):

        antes = (
            productos_dict(prod_ant)
            if afecta_stock(est_ant, obs_ant)
            else {}
        )

        despues = (
            productos_dict(prod_nuevo)
            if afecta_stock(est_nuevo, obs_nuevo)
            else {}
        )

        return {
            sku: antes.get(sku, 0) - despues.get(sku, 0)
            for sku in set(antes) | set(despues)
            if antes.get(sku, 0) != despues.get(sku, 0)
        }

    def limpiar_json(valor):
        if pd.isna(valor):
            return None

        if isinstance(
            valor,
            (pd.Timestamp, datetime.datetime, datetime.date)
        ):
            return valor.strftime("%Y-%m-%d")

        if hasattr(valor, "item"):
            return valor.item()

        return valor


    # =========================================================
    # MENSAJE PERSISTENTE DEL ÚLTIMO CAMBIO
    # =========================================================

    if st.session_state.get("ultimo_mensaje"):

        msg = st.session_state["ultimo_mensaje"]

        st.success(msg["titulo"])

        if msg.get("detalle"):
            st.caption(msg["detalle"])

        movimientos = msg.get("movimientos", [])

        if movimientos:
            st.info("📦 Movimientos de inventario:")

            for m in movimientos:
                signo = "+" if m["ajuste"] > 0 else ""

                st.write(
                    f"**{m['pedido']}** · {m['sku']}: "
                    f"{m['antes']} → {m['despues']} "
                    f"({signo}{m['ajuste']})"
                )

        elif msg.get("sin_stock"):
            st.info("ℹ️ No hubo movimientos de inventario.")


    # =========================================================
    # PEDIDOS
    # =========================================================

    if ped_global is None:
        st.info("No hay pedidos para editar.")

    else:
        df = pd.DataFrame(ped_global)

        if df.empty:
            st.info("No hay pedidos para editar.")

        else:

            # =================================================
            # BUSCADOR
            # =================================================

            buscar = st.text_input("🔍 Buscar pedido:")

            if buscar:
                mask = df.astype(str).apply(
                    lambda x: x.str.contains(
                        buscar,
                        case=False,
                        na=False
                    )
                ).any(axis=1)

                df = df[mask]

            df = df.head(100).reset_index(drop=True)
            df.insert(0, "🗑️ Eliminar", False)

            # =================================================
            # EDITOR
            # =================================================

            editor_key = "editor_editar_pedidos"

            editado = st.data_editor(
                df,
                key=editor_key,
                use_container_width=True,
                hide_index=True,
                disabled=["id_pedido"],
                column_config={
                    "medio": st.column_config.SelectboxColumn(
                        "Medio",
                        options=opciones_medio
                    ),
                    "estado": st.column_config.SelectboxColumn(
                        "Estado",
                        options=opciones_estado_todas
                    ),
                    "🗑️ Eliminar":
                        st.column_config.CheckboxColumn(
                            "Eliminar"
                        ),
                    "monto":
                        st.column_config.NumberColumn(
                            "Monto",
                            format="%.2f"
                        )
                }
            )

            estado_editor = st.session_state.get(
                editor_key,
                {}
            )

            filas_editadas = estado_editor.get(
                "edited_rows",
                {}
            )

            c1, c2 = st.columns(2)

            # =================================================
            # GUARDAR
            # =================================================

            with c1:

                if st.button(
                    "💾 Guardar Ediciones",
                    use_container_width=True
                ):

                    try:
                        # Solo cambios reales.
                        # Marcar "Eliminar" no cuenta como edición.
                        cambios = {
                            int(i): {
                                k: v
                                for k, v in campos.items()
                                if k != "🗑️ Eliminar"
                            }
                            for i, campos in filas_editadas.items()
                            if any(
                                k != "🗑️ Eliminar"
                                for k in campos
                            )
                        }

                        if not cambios:
                            st.warning(
                                "⚠️ No realizaste cambios."
                            )

                        else:
                            inventario = {
                                x["sku"]: x
                                for x in (inv_global or [])
                            }

                            stock = {
                                sku: x["stock_actual"]
                                for sku, x in inventario.items()
                            }

                            updates = []
                            movimientos = []
                            skus_afectados = set()
                            error = False

                            # =================================
                            # SOLO FILAS MODIFICADAS
                            # =================================

                            for i, campos in cambios.items():

                                anterior = df.iloc[i]
                                nuevo = editado.iloc[i]

                                pedido = str(
                                    anterior["id_pedido"]
                                )

                                prod_ant = str(
                                    anterior["producto"]
                                )

                                est_ant = str(
                                    anterior["estado"]
                                )

                                obs_ant = str(
                                    anterior["observaciones"]
                                )

                                prod_nuevo = (
                                    str(nuevo["producto"]).strip()
                                    if pd.notna(nuevo["producto"])
                                    else ""
                                )

                                est_nuevo = (
                                    str(nuevo["estado"]).strip()
                                    if pd.notna(nuevo["estado"])
                                    else ""
                                )

                                obs_nuevo = (
                                    str(nuevo["observaciones"])
                                    if pd.notna(
                                        nuevo["observaciones"]
                                    )
                                    else ""
                                )

                                # Validar SKU
                                nuevos_productos = productos_dict(
                                    prod_nuevo
                                )

                                invalidos = [
                                    sku
                                    for sku in nuevos_productos
                                    if sku not in inventario
                                ]

                                if invalidos:
                                    st.error(
                                        f"❌ {pedido}: SKU "
                                        f"{', '.join(invalidos)} "
                                        f"no existe."
                                    )
                                    error = True
                                    break

                                # Calcular stock
                                ajustes = ajuste_stock(
                                    prod_ant,
                                    est_ant,
                                    obs_ant,
                                    prod_nuevo,
                                    est_nuevo,
                                    obs_nuevo
                                )

                                for sku, cantidad in ajustes.items():

                                    if sku not in stock:
                                        st.error(
                                            f"❌ SKU {sku} "
                                            f"no existe."
                                        )
                                        error = True
                                        break

                                    antes = stock[sku]
                                    stock[sku] += cantidad

                                    movimientos.append({
                                        "pedido": pedido,
                                        "sku": sku,
                                        "antes": antes,
                                        "despues": stock[sku],
                                        "ajuste": cantidad
                                    })

                                    skus_afectados.add(sku)

                                if error:
                                    break

                                # Solo mandar campos editados
                                datos = {
                                    campo: limpiar_json(valor)
                                    for campo, valor in campos.items()
                                    if campo != "id_pedido"
                                }

                                if datos:
                                    updates.append(
                                        (pedido, datos)
                                    )

                            # =================================
                            # ACTUALIZAR SUPABASE
                            # =================================

                            if not error:

                                for pedido, datos in updates:
                                    supabase.table(
                                        "pedidos"
                                    ).update(
                                        datos
                                    ).eq(
                                        "id_pedido",
                                        pedido
                                    ).execute()

                                for sku in skus_afectados:
                                    supabase.table(
                                        "inventario"
                                    ).update({
                                        "stock_actual": stock[sku]
                                    }).eq(
                                        "sku",
                                        sku
                                    ).execute()

                                # Mensaje queda guardado
                                st.session_state[
                                    "ultimo_mensaje"
                                ] = {
                                    "titulo":
                                        "✅ Cambios guardados correctamente.",
                                    "detalle":
                                        f"✏️ {len(updates)} pedido(s) actualizado(s).",
                                    "movimientos":
                                        movimientos,
                                    "sin_stock":
                                        not bool(movimientos)
                                }

                                cargar_todo.clear()
                                st.rerun()

                    except Exception as e:
                        st.error(
                            f"❌ Error al guardar: {e}"
                        )


            # =================================================
            # ELIMINAR
            # =================================================

            with c2:

                if st.button(
                    "🗑️ Eliminar Seleccionados",
                    use_container_width=True
                ):

                    try:
                        seleccionados = editado[
                            editado["🗑️ Eliminar"] == True
                        ]

                        if seleccionados.empty:
                            st.warning(
                                "⚠️ No seleccionaste pedidos."
                            )

                        else:
                            inventario = {
                                x["sku"]: x
                                for x in (inv_global or [])
                            }

                            stock = {
                                sku: x["stock_actual"]
                                for sku, x in inventario.items()
                            }

                            eliminar = []
                            movimientos = []
                            skus_afectados = set()
                            error = False

                            for _, row in seleccionados.iterrows():

                                pedido = str(
                                    row["id_pedido"]
                                )

                                producto = str(
                                    row["producto"]
                                )

                                estado = str(
                                    row["estado"]
                                )

                                obs = str(
                                    row["observaciones"]
                                )

                                # Devolver stock si corresponde
                                if afecta_stock(
                                    estado,
                                    obs
                                ):
                                    for sku, cantidad in (
                                        productos_dict(
                                            producto
                                        ).items()
                                    ):

                                        if sku not in stock:
                                            st.error(
                                                f"❌ {pedido}: "
                                                f"SKU {sku} "
                                                f"no existe."
                                            )
                                            error = True
                                            break

                                        antes = stock[sku]
                                        stock[sku] += cantidad

                                        movimientos.append({
                                            "pedido": pedido,
                                            "sku": sku,
                                            "antes": antes,
                                            "despues": stock[sku],
                                            "ajuste": cantidad
                                        })

                                        skus_afectados.add(
                                            sku
                                        )

                                if error:
                                    break

                                eliminar.append(pedido)

                            # =================================
                            # ACTUALIZAR
                            # =================================

                            if not error:

                                for sku in skus_afectados:
                                    supabase.table(
                                        "inventario"
                                    ).update({
                                        "stock_actual":
                                            stock[sku]
                                    }).eq(
                                        "sku",
                                        sku
                                    ).execute()

                                for pedido in eliminar:
                                    supabase.table(
                                        "pedidos"
                                    ).delete().eq(
                                        "id_pedido",
                                        pedido
                                    ).execute()

                                st.session_state[
                                    "ultimo_mensaje"
                                ] = {
                                    "titulo":
                                        "✅ Pedidos eliminados correctamente.",
                                    "detalle":
                                        f"🗑️ {len(eliminar)} pedido(s) eliminado(s).",
                                    "movimientos":
                                        movimientos,
                                    "sin_stock":
                                        not bool(movimientos)
                                }

                                cargar_todo.clear()
                                st.rerun()

                    except Exception as e:
                        st.error(
                            f"❌ Error al eliminar: {e}"
                        )
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
            
        df_costos_secretos = df_inv[['sku', 'costo']].copy() if 'costo' in df_inv.columns else pd.DataFrame(columns=['sku', 'costo'])
            
        if 'costo' in df_inv.columns:
            df_inv = df_inv.drop(columns=['costo'])
        
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
                
                if not df_costos_secretos.empty:
                    df_il = df_il.merge(df_costos_secretos, on='sku', how='left')
                    df_il['costo'] = pd.to_numeric(df_il['costo'], errors='coerce').fillna(0.0)
                
                try:
                    supabase.table("inventario").delete().neq("sku", "BORRAR_TODO").execute()
                    supabase.table("inventario").insert(df_il.to_dict('records')).execute()
                    st.success("✅ Actualizado de forma segura. Costos protegidos.")
                    cargar_todo.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error guardando inventario: {e}")
            else:
                st.warning("⚠️ No hay datos válidos para guardar.")
                
        st.divider()
        st.subheader("🛒 Alertas de Reposición")
        
        if not df_inv.empty:
            df_inv['stock_actual'] = pd.to_numeric(df_inv['stock_actual'], errors='coerce').fillna(0)
            df_inv['stock_minimo'] = pd.to_numeric(df_inv.get('stock_minimo', 0), errors='coerce').fillna(0)
            df_inv['stock_ideal'] = pd.to_numeric(df_inv.get('stock_ideal', 0), errors='coerce').fillna(0)
            
            condicion_stock_bajo = df_inv['stock_actual'] <= df_inv['stock_minimo']
            condicion_descontinuado = (df_inv['stock_minimo'] == 0) & (df_inv['stock_ideal'] == 0)
            
            df_reposicion = df_inv[condicion_stock_bajo & ~condicion_descontinuado].copy()
            
            if not df_reposicion.empty:
                df_reposicion['Faltante a Comprar'] = df_reposicion['stock_ideal'] - df_reposicion['stock_actual']
                df_reposicion['Faltante a Comprar'] = df_reposicion['Faltante a Comprar'].apply(lambda x: int(x) if x > 0 else 0)
                
                columnas_mostrar = ['sku', 'nombre', 'stock_actual', 'stock_minimo', 'Faltante a Comprar']
                
                st.warning(f"⚠️ Tienes {len(df_reposicion)} productos activos con stock bajo o agotado.")
                st.dataframe(df_reposicion[columnas_mostrar].style.apply(lambda x: ['background-color: #ffebee'] * len(x), axis=1), use_container_width=True, hide_index=True)
            else:
                st.success("✅ Todo tu inventario activo está por encima del nivel mínimo. ¡No hay urgencias de compra!")

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
                
                df_ps = st.data_editor(
                    df_prov[['id_pedido', 'nombre', 'celular', 'monto', 'direccion', 'adelanto', 'deuda', 'clave', 'estado']], 
                    disabled=["id_pedido", "nombre", "celular", "monto", "direccion", "adelanto", "deuda", "clave"], 
                    column_config={
                        "estado": st.column_config.SelectboxColumn("Estado", options=opciones_estado_todas),
                        "monto": st.column_config.NumberColumn("Monto", format="%.2f"),
                        "adelanto": st.column_config.NumberColumn("Adelanto", format="%.2f"),
                        "deuda": st.column_config.NumberColumn("Deuda", format="%.2f")
                    }, 
                    use_container_width=True, 
                    hide_index=True
                )
                
                if st.button("💾 Guardar Shalom"):
                    for index, row in df_ps.iterrows():
                        est_ant = df_prov.loc[index, 'estado']
                        obs_str = df_prov.loc[index, 'observaciones']
                        if row['estado'] != est_ant:
                            procesar_cambio_estado_con_stock(row['id_pedido'], est_ant, row['estado'], df_prov.loc[index, 'producto'], obs_str)
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
                        hora_actual = obtener_fecha_peru("%Y-%m-%d %H:%M:%S")
                        registros_historial = []
                        
                        for idx, row in df_v.iterrows(): 
                            supabase.table("inventario").update({"stock_actual": inv_db[row['sku']]['stock_actual'] + row['cantidad']}).eq("sku", row['sku']).execute()
                            
                            registros_historial.append({
                                "fecha": hora_actual,
                                "sku": row['sku'],
                                "producto": row['Producto'],
                                "cantidad": row['cantidad']
                            })
                        
                        supabase.table("historial_ingresos").insert(registros_historial).execute()
                        
                        st.success("✅ Stock sumado exitosamente.")
                        st.session_state['limpiador_ingreso'] += 1
                        cargar_todo.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error sumando stock: {e}")
                        
        st.divider()
        c_tit, c_filtro = st.columns([2, 1])
        with c_tit:
            st.subheader("📋 Historial de Ingresos")
        with c_filtro:
            fecha_peru_hoy = datetime.datetime.strptime(obtener_fecha_peru("%Y-%m-%d"), "%Y-%m-%d").date()
            fecha_historial = st.date_input("📅 Consultar fecha:", fecha_peru_hoy)
        
        try:
            historial_db = supabase.table("historial_ingresos").select("*").order("fecha", desc=True).limit(2000).execute().data
            if historial_db:
                df_historial = pd.DataFrame(historial_db)
                df_historial['fecha_corta'] = pd.to_datetime(df_historial['fecha']).dt.date
                
                df_filtrado = df_historial[df_historial['fecha_corta'] == fecha_historial].copy()
                
                if not df_filtrado.empty:
                    df_filtrado = df_filtrado.rename(columns={"fecha": "Hora del Ingreso", "sku": "SKU", "producto": "Producto", "cantidad": "Cant. Ingresada"})
                    st.dataframe(df_filtrado[['Hora del Ingreso', 'SKU', 'Producto', 'Cant. Ingresada']], use_container_width=True, hide_index=True)
                else:
                    st.info(f"No hay mercadería ingresada el {fecha_historial.strftime('%d/%m/%Y')}.")
            else:
                st.info("Aún no hay registros guardados en la base de datos.")
        except Exception as e:
            st.warning("⚠️ Recuerda crear la tabla 'historial_ingresos' en Supabase para que este cuadro funcione.")

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
