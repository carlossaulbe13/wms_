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

# --- CONFIGURACIÓN DE NUBE (FIREBASE) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"

def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception as e:
        st.error(f"Error de conexión con Firebase: {e}")
    return {}

def guardar_db(db):
    try:
        requests.put(FIREBASE_URL, json=db)
    except Exception as e:
        st.error(f"Error al guardar en Firebase: {e}")

# --- CONFIGURACIÓN MQTT ---
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC = "almacen/escaneo"

# --- ALGORITMO DE AUTO-ASIGNACIÓN ---
def obtener_coordenada_libre(db, rack_objetivo):
    ocupadas = [(v.get('piso'), v.get('fila'), v.get('columna')) for v in db.values() if v.get('rack') == rack_objetivo]
    for p in range(1, 6):
        for f in range(1, 4):
            for c in range(1, 5):
                if (p, f, c) not in ocupadas:
                    return p, f, c
    return None, None, None

# --- INICIALIZACIÓN DE ESTADOS ---
if 'db' not in st.session_state:
    st.session_state.db = cargar_db()
if 'sku_pendiente' not in st.session_state:
    st.session_state.sku_pendiente = None
if 'ultimo_sku_procesado' not in st.session_state:
    st.session_state.ultimo_sku_procesado = None

# --- CONEXIÓN MQTT ---
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()
        st.session_state.mqtt_client = client
    except:
        pass

# --- INTERFAZ UMAD ---
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>UMAD Warehouse Management System</h1>", unsafe_allow_html=True)

tabs = st.tabs(["Monitoreo y Ubicación", "Escáner de Campo", "Maestro de Artículos"])

# --- PESTAÑA 1: MONITOR (TIEMPO REAL) ---
with tabs[0]:
    st_autorefresh(interval=3000, key="datarefresh")
    st.session_state.db = cargar_db()

    st.header("Mapa de Racks en Tiempo Real")
    col1, col2 = st.columns(2)
    with col1:
        r_sel = st.selectbox("Rack:", ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"])
    with col2:
        p_sel = st.selectbox("Piso:", [1, 2, 3, 4, 5])

    for fila in range(1, 4):
        cols = st.columns(4)
        for col in range(1, 5):
            item = next((v for v in st.session_state.db.values() if v.get('rack')==r_sel and v.get('piso')==p_sel and v.get('fila')==fila and v.get('columna')==col), None)
            with cols[col-1]:
                if item:
                    es_congelado = item.get('estado') == "CONGELADO"
                    bg = "#f8d7da" if es_congelado else "#fff3cd"
                    border = "#dc3545" if es_congelado else "#ffc107"
                    piezas = item.get('cantidad', 1)
                    sku_base = item.get('sku_base', 'N/A')
                    
                    st.markdown(f"<div style='background-color:{bg}; border:3px solid {border}; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'><b>{item['nombre']}</b><br><small>SKU: {sku_base}</small><br><small><b>{piezas} pzas</b> | {item.get('estado','ACTIVO')}</small><br><small>F{fila}-C{col}</small></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='background-color:#d4edda; border:3px solid #28a745; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'><b>DISPONIBLE</b><br><small>F{fila}-C{col}</small></div>", unsafe_allow_html=True)

# --- PESTAÑA 2: ESCÁNER DE CAMPO ---
with tabs[1]:
    st.subheader("Captura de Pallet Físico")
    
    if st.session_state.sku_pendiente is None:
        foto = st.camera_input("Escanea el código QR del Pallet:")
        if foto:
            img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
            qrs = decode(img)
            if qrs:
                uid_pallet = qrs[0].data.decode('utf-8').strip().upper()
                
                if uid_pallet in st.session_state.db:
                    item = st.session_state.db[uid_pallet]
                    if item.get('estado') == "CONGELADO":
                        st.error(f"⚠️ EL PALLET {uid_pallet} ESTÁ CONGELADO. NO MOVER.")
                    else:
                        if uid_pallet != st.session_state.ultimo_sku_procesado:
                            st.success(f"📦 Identificado: {item['nombre']} ({item.get('cantidad', 1)} pzas) | Rack actual: {item['rack']}")
                            st.session_state.mqtt_client.publish(TOPIC, item['rack'])
                            st.toast(f"Comando {item['rack']} enviado al ESP32", icon="✅")
                            st.session_state.ultimo_sku_procesado = uid_pallet
                        else:
                            st.info(f"Visualizando Pallet en {item['rack']}. (Hardware activado).")
                else:
                    st.session_state.sku_pendiente = uid_pallet
                    st.session_state.ultimo_sku_procesado = None
                    st.rerun()
        else:
            st.session_state.ultimo_sku_procesado = None

    else:
        st.warning(f"QR de Pallet Nuevo Detectado: {st.session_state.sku_pendiente}")
        st.info("Asigna el SKU (pieza) y la cantidad a esta matrícula de pallet.")
        with st.form("reg_cloud"):
            c_sku, c_nom = st.columns(2)
            with c_sku: sku_base = st.text_input("SKU / Número de Parte de la Pieza")
            with c_nom: nom = st.text_input("Descripción de la Pieza")
            
            c_peso, c_cant = st.columns(2)
            with c_peso: peso = st.number_input("Peso total del Pallet (kg)", min_value=0.0)
            with c_cant: cant = st.number_input("Cantidad de piezas en el pallet", min_value=1, value=1)
            
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("Largo (cm)", min_value=0.0)
            with c2: a = st.number_input("Ancho (cm)", min_value=0.0)
            with c3: h = st.number_input("Alto (cm)", min_value=0.0)
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1: submit = st.form_submit_button("Registrar Pallet y Almacenar")
            with col_btn2: cancelar = st.form_submit_button("Cancelar Escaneo")
            
            if cancelar:
                st.session_state.sku_pendiente = None
                st.rerun()
                
            if submit and nom and sku_base:
                vol = (l*a*h)/1000000
                rack = "POS_4" if peso >= 100 or vol > 1.5 else "POS_1"
                piso, fila, col = obtener_coordenada_libre(st.session_state.db, rack)
                
                if piso is not None:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "sku_base": sku_base, "nombre": nom, "peso": peso, "cantidad": cant, 
                        "volumen": vol, "rack": rack, "piso": piso, "fila": fila, "columna": col, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.session_state.mqtt_client.publish(TOPIC, rack)
                    st.session_state.sku_pendiente = None
                    st.success("Pallet registrado en Firebase y Rack activado.")
                    st.rerun()
                else:
                    st.error(f"El {rack} está completamente lleno. Reubica materiales para liberar espacio.")

# --- PESTAÑA 3: MAESTRO DE ARTÍCULOS ---
with tabs[2]:
    st.header("Gestión del Inventario")
    db_actual = cargar_db()
    
    if db_actual:
        data_tabla = []
        for k, v in db_actual.items():
            data_tabla.append({
                "QR del Pallet": k,
                "SKU Pieza": v.get('sku_base', 'N/A'),
                "Nombre": v.get('nombre', ''),
                "Piezas": v.get('cantidad', 1),
                "Rack": v.get('rack', ''),
                "Piso": v.get('piso', ''),
                "Fila": v.get('fila', ''),
                "Col": v.get('columna', ''),
                "Estado": v.get('estado', 'ACTIVO')
            })
            
        df = pd.DataFrame(data_tabla)
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=True)
        grid_response = AgGrid(df, gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, theme='streamlit')
        
        sel = grid_response['selected_rows']
        if sel is not None and len(sel) > 0:
            item_sel = sel.iloc[0].to_dict() if isinstance(sel, pd.DataFrame) else sel[0]
            uid_real = item_sel['QR del Pallet']
            datos_reales = db_actual[uid_real]
            
            st.divider()
            st.write(f"### Editando Matrícula: {uid_real}")
            
            col_ed1, col_ed2, col_ed3 = st.columns(3)
            with col_ed1:
                nuevo_sku = st.text_input("SKU Base", value=datos_reales.get('sku_base', ''))
                nuevo_nombre = st.text_input("Nombre", value=datos_reales['nombre'])
            with col_ed2:
                nueva_cant = st.number_input("Piezas", min_value=1, value=int(datos_reales.get('cantidad', 1)))
            with col_ed3:
                nuevo_estado = st.selectbox("Estado", ["ACTIVO", "CONGELADO"], index=0 if datos_reales.get('estado')=="ACTIVO" else 1)
            
            st.write("Dimensiones y Peso")
            col_p, col_v = st.columns(2)
            with col_p:
                nuevo_peso = st.number_input("Peso (kg)", min_value=0.0, value=float(datos_reales.get('peso', 0.0)))
            with col_v:
                nuevo_vol = st.number_input("Volumen (m³)", min_value=0.0, value=float(datos_reales.get('volumen', 0.0)), step=0.1)
            
            rack_actual = datos_reales.get('rack', 'POS_2')
            rack_ideal = "POS_4" if nuevo_peso >= 100 or nuevo_vol > 1.5 else ("POS_3" if nuevo_peso >= 50 or nuevo_vol > 1.0 else ("POS_1" if nuevo_vol < 0.5 and nuevo_peso < 20 else "POS_2"))
            
            if rack_actual != rack_ideal:
                st.warning(f"⚠️ Alerta Operativa: Por las nuevas dimensiones/peso, este material debería reubicarse físicamente en **{rack_ideal}** en lugar de su posición actual ({rack_actual}).")

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Guardar Cambios"):
                    db_actual[uid_real]['sku_base'] = nuevo_sku
                    db_actual[uid_real]['nombre'] = nuevo_nombre
                    db_actual[uid_real]['cantidad'] = nueva_cant
                    db_actual[uid_real]['estado'] = nuevo_estado
                    db_actual[uid_real]['peso'] = nuevo_peso
                    db_actual[uid_real]['volumen'] = nuevo_vol
                    guardar_db(db_actual)
                    st.success("Cambios guardados.")
                    st.rerun()
            with col_b:
                if st.button("Eliminar Pallet de la Nube"):
                    del db_actual[uid_real]
                    guardar_db(db_actual)
                    st.rerun()

    with st.expander("➕ Alta de Materiales y Asignación Manual"):
        with st.form("new_part_manual"):
            new_uid = st.text_input("ID Único del Pallet (Ej. PALLET-010)").upper()
            c_sk, c_nm = st.columns(2)
            with c_sk: new_sku_base = st.text_input("SKU Genérico")
            with c_nm: new_name = st.text_input("Descripción")
            
            c_p, c_c = st.columns(2)
            with c_p: p = st.number_input("Peso (kg)", min_value=0.0)
            with c_c: cant_manual = st.number_input("Cantidad de piezas", min_value=1, value=1)
            
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("Largo (cm)", min_value=0.0)
            with c2: a = st.number_input("Ancho (cm)", min_value=0.0)
            with c3: h = st.number_input("Alto (cm)", min_value=0.0)
            
            generar_qr_fisico = st.checkbox("Generar e imprimir código QR físico", value=True)
            
            if st.form_submit_button("Registrar Material"):
                vol = (l/100) * (a/100) * (h/100)
                if p >= 200 or vol > 2.0: r = "POS_4"
                elif p >= 50 or vol > 1.0: r = "POS_3"
                elif vol < 0.5 and p < 20: r = "POS_1"
                else: r = "POS_2"
                
                piso, fila, columna = obtener_coordenada_libre(st.session_state.db, r)
                
                if piso is None:
                    st.error(f"El {r} está lleno.")
                else:
                    st.session_state.db[new_uid] = {
                        "sku_base": new_sku_base, "nombre": new_name, "peso": p, "cantidad": cant_manual, 
                        "volumen": vol, "rack": r, "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    
                    if generar_qr_fisico:
                        qr_img = qrcode.make(new_uid)
                        qr_img.save(f"label_{new_uid}.png")
                        st.image(f"label_{new_uid}.png", width=200)
                        
                    st.success(f"Registrado en {r} (P{piso}-F{fila}-C{columna}).")
