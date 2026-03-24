import streamlit as st
import paho.mqtt.client as mqtt
import json
import requests
import cv2
import numpy as np
import pandas as pd
from pyzbar.pyzbar import decode
import qrcode
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_autorefresh import st_autorefresh
import time

# --- CONFIGURACION DE NUBE (FIREBASE) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"

def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception as e:
        st.error(f"ERROR DE CONEXION CON FIREBASE: {e}")
    return {}

def guardar_db(db):
    try:
        requests.put(FIREBASE_URL, json=db)
    except Exception as e:
        st.error(f"ERROR AL GUARDAR EN FIREBASE: {e}")

# --- CONFIGURACION MQTT ---
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC_PUB = "almacen/escaneo"
TOPIC_SUB = "almacen/confirmacion"

# --- PUENTE SEGURO ENTRE HILOS PARA MQTT ---
if 'msg_mqtt_recibido' not in st.session_state:
    st.session_state.msg_mqtt_recibido = None

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    if payload.endswith("_OFF"):
        st.session_state.msg_mqtt_recibido = payload.replace("_OFF", "")

def obtener_coordenada_libre(db, rack_objetivo):
    ocupadas = [(v.get('piso'), v.get('fila'), v.get('columna')) for v in db.values() if v.get('rack') == rack_objetivo]
    for p in range(1, 6):
        for f in range(1, 4):
            for c in range(1, 5):
                if (p, f, c) not in ocupadas:
                    return p, f, c
    return None, None, None

# --- INICIALIZACION DE ESTADOS ---
if 'db' not in st.session_state:
    st.session_state.db = cargar_db()
if 'sku_pendiente' not in st.session_state:
    st.session_state.sku_pendiente = None
if 'ultimo_sku_procesado' not in st.session_state:
    st.session_state.ultimo_sku_procesado = None
if 'confirmacion_pendiente' not in st.session_state:
    st.session_state.confirmacion_pendiente = None
if 'qr_generado' not in st.session_state:
    st.session_state.qr_generado = None

# --- CONEXION MQTT ---
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    client.on_message = on_message
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.subscribe(TOPIC_SUB)
        client.loop_start()
        st.session_state.mqtt_client = client
    except:
        pass

# --- LOGICA DE ACTUALIZACION DE ESTADO MQTT ---
if st.session_state.msg_mqtt_recibido:
    if st.session_state.confirmacion_pendiente == st.session_state.msg_mqtt_recibido:
        st.session_state.confirmacion_pendiente = None
    st.session_state.msg_mqtt_recibido = None 

# --- INTERFAZ UMAD ---
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>UMAD Warehouse Management System</h1>", unsafe_allow_html=True)

# --- PANEL GLOBAL DE CONFIRMACION ---
if st.session_state.confirmacion_pendiente:
    st.warning(f"ACCION REQUERIDA: El LED del Rack {st.session_state.confirmacion_pendiente} esta ENCENDIDO. Confirma fisicamente con el boton o hazlo manual aqui:")
    if st.button(f"[ CONFIRMAR MANUALMENTE - APAGAR LED DE {st.session_state.confirmacion_pendiente} ]"):
        st.session_state.mqtt_client.publish(TOPIC_PUB, f"{st.session_state.confirmacion_pendiente}_OFF")
        st.session_state.confirmacion_pendiente = None
        st.rerun()
    st.divider()

tabs = st.tabs(["MONITOREO Y UBICACION", "ESCANER DE CAMPO", "MAESTRO DE ARTICULOS"])

# --- PESTANA 1: MONITOR (TIEMPO REAL) ---
with tabs[0]:
    st_autorefresh(interval=3000, key="datarefresh")
    st.session_state.db = cargar_db()

    st.header("MAPA DE RACKS Y BUSCADOR")
    busqueda = st.text_input("BUSCAR MATERIAL POR NOMBRE, SKU O MATRICULA:", "").strip().upper()

    default_rack = st.session_state.get('last_rack', "POS_1")
    default_piso = st.session_state.get('last_piso', 1)

    if busqueda:
        for k, v in st.session_state.db.items():
            if busqueda in v['nombre'].upper() or busqueda in v.get('sku_base', '').upper() or busqueda in k.upper():
                default_rack = v.get('rack', default_rack)
                default_piso = v.get('piso', default_piso)
                break 

    racks_list = ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"]
    pisos_list = [1, 2, 3, 4, 5]

    col1, col2 = st.columns(2)
    with col1:
        r_sel = st.selectbox("RACK:", racks_list, index=racks_list.index(default_rack) if default_rack in racks_list else 0)
    with col2:
        p_sel = st.selectbox("PISO:", pisos_list, index=pisos_list.index(default_piso) if default_piso in pisos_list else 0)

    st.session_state.last_rack = r_sel
    st.session_state.last_piso = p_sel

    style_base = "border-radius:10px; padding:10px; text-align:center; color:black; height:150px; display:flex; flex-direction:column; justify-content:center; align-items:center; overflow:hidden;"

    for fila in range(1, 4):
        cols = st.columns(4)
        for col in range(1, 5):
            item = None
            item_key = None
            for k, v in st.session_state.db.items():
                if v.get('rack') == r_sel and v.get('piso') == p_sel and v.get('fila') == fila and v.get('columna') == col:
                    item = v
                    item_key = k
                    break
            
            with cols[col-1]:
                if item:
                    es_congelado = item.get('estado') == "CONGELADO"
                    es_buscado = busqueda != "" and (busqueda in item['nombre'].upper() or busqueda in item.get('sku_base', '').upper() or busqueda in item_key.upper())
                    
                    if es_buscado:
                        bg, border = "#cce5ff", "#004085"
                    else:
                        bg = "#f8d7da" if es_congelado else "#fff3cd"
                        border = "#dc3545" if es_congelado else "#ffc107"
                        
                    piezas = item.get('cantidad', 1)
                    sku_base = item.get('sku_base', 'N/A')
                    
                    div_html = f"<div style='background-color:{bg}; border:3px solid {border}; {style_base}'>"
                    div_html += f"<b style='font-size: 16px; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; width: 100%;'>{item['nombre']}</b>"
                    div_html += f"<small style='font-size: 13px; line-height: 1.3;'>SKU: {sku_base}<br><b>{piezas} PZAS</b> | {item.get('estado','ACTIVO')}<br>F{fila}-C{col}</small></div>"
                    st.markdown(div_html, unsafe_allow_html=True)
                else:
                    div_html = f"<div style='background-color:#d4edda; border:3px solid #28a745; {style_base}'>"
                    div_html += f"<b style='font-size: 14px;'>DISPONIBLE</b><br><small style='font-size: 13px;'>F{fila}-C{col}</small></div>"
                    st.markdown(div_html, unsafe_allow_html=True)

# --- PESTANA 2: ESCANER DE CAMPO ---
with tabs[1]:
    st.subheader("CAPTURA DE PALLET FISICO")
    
    if st.session_state.sku_pendiente is None:
        foto = st.camera_input("ESCANEA EL CODIGO QR DEL PALLET:")
        if foto:
            img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
            qrs = decode(img)
            if qrs:
                uid_pallet = qrs[0].data.decode('utf-8').strip().upper()
                
                if uid_pallet in st.session_state.db:
                    item = st.session_state.db[uid_pallet]
                    if item.get('estado') == "CONGELADO":
                        st.error(f"ALERTA OPERATIVA: EL PALLET {uid_pallet} ESTA CONGELADO. NO MOVER.")
                    else:
                        if uid_pallet != st.session_state.ultimo_sku_procesado:
                            st.success(f"IDENTIFICADO: {item['nombre']} ({item.get('cantidad', 1)} pzas) | RACK ACTUAL: {item['rack']}")
                            st.session_state.mqtt_client.publish(TOPIC_PUB, f"{item['rack']}_ON")
                            st.session_state.confirmacion_pendiente = item['rack']
                            st.session_state.ultimo_sku_procesado = uid_pallet
                            st.rerun()
                        else:
                            st.info(f"INFO: Visualizando Pallet en {item['rack']}. (Hardware activado).")
                else:
                    st.session_state.sku_pendiente = uid_pallet
                    st.session_state.ultimo_sku_procesado = None
                    st.rerun()
        else:
            st.session_state.ultimo_sku_procesado = None

    else:
        st.warning(f"INFO: QR DE PALLET NUEVO DETECTADO: {st.session_state.sku_pendiente}")
        with st.form("reg_cloud"):
            c_sku, c_nom = st.columns(2)
            with c_sku: sku_base = st.text_input("SKU / NUMERO DE PARTE DE LA PIEZA")
            with c_nom: nom = st.text_input("DESCRIPCION DE LA PIEZA")
            
            c_peso, c_cant = st.columns(2)
            with c_peso: peso = st.number_input("PESO TOTAL DEL PALLET (KG)", min_value=0.0)
            with c_cant: cant = st.number_input("CANTIDAD DE PIEZAS EN EL PALLET", min_value=1, value=1)
            
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("LARGO (CM)", min_value=0.0)
            with c2: a = st.number_input("ANCHO (CM)", min_value=0.0)
            with c3: h = st.number_input("ALTO (CM)", min_value=0.0)
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1: submit = st.form_submit_button("REGISTRAR PALLET Y ALMACENAR")
            with col_btn2: cancelar = st.form_submit_button("CANCELAR ESCANEO")
            
            if cancelar:
                st.session_state.sku_pendiente = None
                st.rerun()
                
            if submit and nom and sku_base:
                vol = (l*a*h)/1000000
                
                # --- LÓGICA DE 5 RACKS (ALGORITMO) ---
                if peso >= 100: rack = "POS_4"
                elif vol > 1.5: rack = "POS_5"
                elif peso >= 50 or vol > 1.0: rack = "POS_3"
                elif peso >= 20 or vol > 0.5: rack = "POS_2"
                else: rack = "POS_1"
                
                piso, fila, col = obtener_coordenada_libre(st.session_state.db, rack)
                
                if piso is not None:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "sku_base": sku_base, "nombre": nom, "peso": peso, "cantidad": cant, 
                        "volumen": vol, "rack": rack, "piso": piso, "fila": fila, "columna": col, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.session_state.mqtt_client.publish(TOPIC_PUB, f"{rack}_ON")
                    time.sleep(0.1) # Pequeña pausa de red para asegurar que el comando MQTT salga antes de recargar
                    st.session_state.confirmacion_pendiente = rack
                    st.session_state.sku_pendiente = None
                    st.success("EXITO: PALLET REGISTRADO EN FIREBASE Y RACK ACTIVADO.")
                    st.rerun()
                else:
                    st.error(f"ERROR OPERATIVO: EL {rack} ESTA COMPLETAMENTE LLENO. REUBICA MATERIALES.")

# --- PESTANA 3: MAESTRO DE ARTICULOS ---
with tabs[2]:
    st.header("GESTION DEL INVENTARIO")
    db_actual = cargar_db()
    
    if db_actual:
        data_tabla = []
        for k, v in db_actual.items():
            data_tabla.append({
                "MATRICULA (QR)": k,
                "SKU": v.get('sku_base', 'N/A'),
                "NOMBRE": v.get('nombre', ''),
                "PZAS": v.get('cantidad', 1),
                "RACK": v.get('rack', ''),
                "PISO": v.get('piso', ''),
                "FILA": v.get('fila', ''),
                "COL": v.get('columna', ''),
                "ESTADO": v.get('estado', 'ACTIVO')
            })
            
        df = pd.DataFrame(data_tabla)
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=True)
        grid_response = AgGrid(df, gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, theme='streamlit')
        
        sel = grid_response['selected_rows']
        if sel is not None and len(sel) > 0:
            item_sel = sel.iloc[0].to_dict() if isinstance(sel, pd.DataFrame) else sel[0]
            uid_real = item_sel['MATRICULA (QR)']
            datos_reales = db_actual[uid_real]
            
            st.divider()
            st.write(f"### EDITANDO MATRICULA: {uid_real}")
            
            col_ed1, col_ed2, col_ed3 = st.columns(3)
            with col_ed1:
                nuevo_sku = st.text_input("SKU BASE", value=datos_reales.get('sku_base', ''))
                nuevo_nombre = st.text_input("NOMBRE", value=datos_reales['nombre'])
            with col_ed2:
                nueva_cant = st.number_input("PIEZAS", min_value=1, value=int(datos_reales.get('cantidad', 1)))
            with col_ed3:
                nuevo_estado = st.selectbox("ESTADO", ["ACTIVO", "CONGELADO"], index=0 if datos_reales.get('estado')=="ACTIVO" else 1)
            
            st.write("DIMENSIONES Y PESO")
            col_p, col_v = st.columns(2)
            with col_p:
                nuevo_peso = st.number_input("PESO (KG)", min_value=0.0, value=float(datos_reales.get('peso', 0.0)))
            with col_v:
                nuevo_vol = st.number_input("VOLUMEN (M3)", min_value=0.0, value=float(datos_reales.get('volumen', 0.0)), step=0.1)
            
            rack_actual = datos_reales.get('rack', 'POS_2')
            
            # --- LÓGICA DE 5 RACKS EN EDICIÓN ---
            if nuevo_peso >= 100: rack_ideal = "POS_4"
            elif nuevo_vol > 1.5: rack_ideal = "POS_5"
            elif nuevo_peso >= 50 or nuevo_vol > 1.0: rack_ideal = "POS_3"
            elif nuevo_peso >= 20 or nuevo_vol > 0.5: rack_ideal = "POS_2"
            else: rack_ideal = "POS_1"
            
            if rack_actual != rack_ideal:
                st.warning(f"ALERTA OPERATIVA: Por las nuevas dimensiones/peso, este material deberia reubicarse fisicamente en {rack_ideal} en lugar de su posicion actual ({rack_actual}).")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("GUARDAR CAMBIOS"):
                    db_actual[uid_real]['sku_base'] = nuevo_sku
                    db_actual[uid_real]['nombre'] = nuevo_nombre
                    db_actual[uid_real]['cantidad'] = nueva_cant
                    db_actual[uid_real]['estado'] = nuevo_estado
                    db_actual[uid_real]['peso'] = nuevo_peso
                    db_actual[uid_real]['volumen'] = nuevo_vol
                    guardar_db(db_actual)
                    st.success("EXITO: CAMBIOS GUARDADOS.")
                    st.rerun()
            with col_b:
                if st.button("ELIMINAR PALLET DE LA NUBE"):
                    del db_actual[uid_real]
                    guardar_db(db_actual)
                    st.rerun()

    with st.expander("ALTA DE MATERIALES Y ASIGNACION MANUAL"):
        with st.form("new_part_manual"):
            new_uid = st.text_input("ID UNICO DEL PALLET (EJ. PALLET-010)").upper()
            c_sk, c_nm = st.columns(2)
            with c_sk: new_sku_base = st.text_input("SKU GENERICO")
            with c_nm: new_name = st.text_input("DESCRIPCION")
            
            c_p, c_c = st.columns(2)
            with c_p: p = st.number_input("PESO (KG)", min_value=0.0)
            with c_c: cant_manual = st.number_input("CANTIDAD DE PIEZAS", min_value=1, value=1)
            
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("LARGO (CM)", min_value=0.0)
            with c2: a = st.number_input("ANCHO (CM)", min_value=0.0)
            with c3: h = st.number_input("ALTO (CM)", min_value=0.0)
            
            generar_qr_fisico = st.checkbox("GENERAR E IMPRIMIR CODIGO QR FISICO", value=True)
            
            if st.form_submit_button("REGISTRAR MATERIAL"):
                vol = (l/100) * (a/100) * (h/100)
                
                # --- LÓGICA DE 5 RACKS EN MANUAL ---
                if p >= 100: r = "POS_4"
                elif vol > 1.5: r = "POS_5"
                elif p >= 50 or vol > 1.0: r = "POS_3"
                elif p >= 20 or vol > 0.5: r = "POS_2"
                else: r = "POS_1"
                
                piso, fila, columna = obtener_coordenada_libre(st.session_state.db, r)
                
                if piso is None:
                    st.error(f"ERROR OPERATIVO: EL {r} ESTA LLENO.")
                else:
                    st.session_state.db[new_uid] = {
                        "sku_base": new_sku_base, "nombre": new_name, "peso": p, "cantidad": cant_manual, 
                        "volumen": vol, "rack": r, "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    
                    if generar_qr_fisico:
                        qr_img = qrcode.make(new_uid)
                        nombre_archivo = f"label_{new_uid}.png"
                        qr_img.save(nombre_archivo)
                        st.session_state.qr_generado = nombre_archivo
                    
                    st.session_state.mqtt_client.publish(TOPIC_PUB, f"{r}_ON")
                    time.sleep(0.1) # Pequeña pausa para evitar Race Condition
                    st.session_state.confirmacion_pendiente = r
                    st.rerun()

        if st.session_state.qr_generado:
            st.success("EXITO: MATERIAL REGISTRADO. ESPERANDO CONFIRMACION FISICA EN EL RACK.")
            st.image(st.session_state.qr_generado, width=200, caption="CODIGO QR LISTO PARA IMPRESION")
            if st.button("LIMPIAR PANTALLA DE IMPRESION"):
                st.session_state.qr_generado = None
                st.rerun()
