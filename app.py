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

# Inicialización
if 'db' not in st.session_state:
    st.session_state.db = cargar_db()
if 'sku_pendiente' not in st.session_state:
    st.session_state.sku_pendiente = None

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
                    st.markdown(f"<div style='background-color:{bg}; border:3px solid {border}; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'><b>{item['nombre']}</b><br><small>{item.get('estado','ACTIVO')}</small><br><small>F{fila}-C{col}</small></div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style='background-color:#d4edda; border:3px solid #28a745; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'><b>DISPONIBLE</b><br><small>F{fila}-C{col}</small></div>", unsafe_allow_html=True)

# --- PESTAÑA 2: ESCÁNER DE CAMPO ---
with tabs[1]:
    st.subheader("Captura de Material")
    
    if st.session_state.sku_pendiente is None:
        foto = st.camera_input("Escanea el código QR:")
        if foto:
            img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
            qrs = decode(img)
            if qrs:
                sku = qrs[0].data.decode('utf-8').strip().upper()
                
                # --- LÓGICA DE RECONOCIMIENTO ---
                if sku in st.session_state.db:
                    item = st.session_state.db[sku]
                    if item.get('estado') == "CONGELADO":
                        st.error(f"⚠️ EL MATERIAL {sku} ESTÁ CONGELADO. NO MOVER.")
                    else:
                        st.success(f"📦 Material: {item['nombre']} | Ubicación: {item['rack']} (P{item['piso']}-F{item['fila']}-C{col})")
                        # ACTIVAR HARDWARE AL INSTANTE
                        st.session_state.mqtt_client.publish(TOPIC, item['rack'])
                        st.toast(f"Comando {item['rack']} enviado al ESP32", icon="✅")
                else:
                    st.session_state.sku_pendiente = sku
                    st.rerun()

    else:
        # Formulario de registro para QR Nuevo
        st.warning(f"QR Nuevo: {st.session_state.sku_pendiente}")
        with st.form("reg_cloud"):
            nom = st.text_input("Descripción")
            peso = st.number_input("Peso (kg)", 0.0)
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("Largo", 0.0)
            with c2: a = st.number_input("Ancho", 0.0)
            with c3: h = st.number_input("Alto", 0.0)
            
            if st.form_submit_button("Registrar y Almacenar"):
                vol = (l*a*h)/1000000
                rack = "POS_4" if peso >= 100 or vol > 1.5 else "POS_1"
                piso, fila, col = obtener_coordenada_libre(st.session_state.db, rack)
                
                if piso:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "nombre": nom, "peso": peso, "volumen": vol, "rack": rack, 
                        "piso": piso, "fila": fila, "columna": col, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.session_state.mqtt_client.publish(TOPIC, rack)
                    st.session_state.sku_pendiente = None
                    st.success("Registrado en Firebase y Rack activado.")
                    st.rerun()

# --- PESTAÑA 3: MAESTRO DE ARTÍCULOS ---
with tabs[2]:
    st.header("Gestión del Inventario")
    db_actual = cargar_db()
    
    if db_actual:
        df = pd.DataFrame([{"SKU": k, **v} for k, v in db_actual.items()])
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=True)
        grid_response = AgGrid(df, gridOptions=gb.build(), update_mode=GridUpdateMode.SELECTION_CHANGED, theme='streamlit')
        
        sel = grid_response['selected_rows']
        if sel is not None and len(sel) > 0:
            item_sel = sel.iloc[0].to_dict() if isinstance(sel, pd.DataFrame) else sel[0]
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button(f"Congelar/Activar {item_sel['SKU']}"):
                    nuevo = "CONGELADO" if item_sel['estado'] == "ACTIVO" else "ACTIVO"
                    db_actual[item_sel['SKU']]['estado'] = nuevo
                    guardar_db(db_actual)
                    st.rerun()
            with col_b:
                if st.button("Eliminar de la Nube"):
                    del db_actual[item_sel['SKU']]
                    guardar_db(db_actual)
                    st.rerun()
