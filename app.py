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
                    # Mostrar la cantidad de piezas en el monitor
                    piezas = item.get('cantidad', 1)
                    
                    st.markdown(f"<div style='background-color:{bg}; border:3px solid {border}; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'><b>{item['nombre']}</b><br><small><b>{piezas} pzas</b> | {item.get('estado','ACTIVO')}</small><br><small>F{fila}-C{col}</small></div>", unsafe_allow_html=True)
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
                
                if sku in st.session_state.db:
                    item = st.session_state.db[sku]
                    if item.get('estado') == "CONGELADO":
                        st.error(f"⚠️ EL MATERIAL {sku} ESTÁ CONGELADO. NO MOVER.")
                    else:
                        # Cerrojo para evitar bucle en ESP32
                        if sku != st.session_state.ultimo_sku_procesado:
                            st.success(f"📦 Material: {item['nombre']} ({item.get('cantidad', 1)} pzas) | Rack: {item['rack']}")
                            st.session_state.mqtt_client.publish(TOPIC, item['rack'])
                            st.toast(f"Comando {item['rack']} enviado al ESP32", icon="✅")
                            st.session_state.ultimo_sku_procesado = sku
                        else:
                            st.info(f"Visualizando: {item['nombre']} en {item['rack']}")
                else:
                    st.session_state.sku_pendiente = sku
                    st.session_state.ultimo_sku_procesado = None
                    st.rerun()
        else:
            st.session_state.ultimo_sku_procesado = None

    else:
        st.warning(f"QR Nuevo: {st.session_state.sku_pendiente}")
        with st.form("reg_cloud"):
            nom = st.text_input("Descripción")
            
            c_peso, c_cant = st.columns(2)
            with c_peso: peso = st.number_input("Peso total (kg)", 0.0)
            with c_cant: cant = st.number_input("Cantidad de piezas", min_value=1, value=1)
            
            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("Largo (cm)", 0.0)
            with c2: a = st.number_input("Ancho (cm)", 0.0)
            with c3: h = st.number_input("Alto (cm)", 0.0)
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1: submit = st.form_submit_button("Registrar y Almacenar")
            with col_btn2: cancelar = st.form_submit_button("Cancelar Escaneo")
            
            if cancelar:
                st.session_state.sku_pendiente = None
                st.rerun()
                
            if submit and nom:
                vol = (l*a*h)/1000000
                rack = "POS_4" if peso >= 100 or vol > 1.5 else "POS_1"
                piso, fila, col = obtener_coordenada_libre(st.session_state.db, rack)
                
                if piso:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "nombre": nom, "peso": peso, "cantidad": cant, "volumen": vol, "rack": rack, 
                        "piso": piso, "fila": fila, "columna": col, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.session_state.mqtt_client.publish(TOPIC, rack)
                    st.session_state.sku_pendiente = None
                    st.success("Registrado en Firebase y Rack activado.")
                    st.rerun()
                else:
                    st.error(f"El {rack} está completamente lleno.")

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
            
            st.divider()
            st.write(f"### Editando: {item_sel['SKU']}")
            col_ed1, col_ed2, col_ed3 = st.columns(3)
            
            with col_ed1:
                nuevo_nombre = st.text_input("Nombre", value=item_sel['nombre'])
            with col_ed2:
                nueva_cant = st.number_input("Piezas", min_value=1, value=int(item_sel.get('cantidad', 1)))
            with col_ed3:
                nuevo_estado = st.selectbox("Estado", ["ACTIVO", "CONGELADO"], index=0 if item_sel.get('estado')=="ACTIVO" else 1)
            
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Guardar Cambios"):
                    db_actual[item_sel['SKU']]['nombre'] = nuevo_nombre
                    db_actual[item_sel['SKU']]['cantidad'] = nueva_cant
                    db_actual[item_sel['SKU']]['estado'] = nuevo_estado
                    guardar_db(db_actual)
                    st.success("Cambios guardados.")
                    st.rerun()
            with col_b:
                if st.button("Eliminar de la Nube"):
                    del db_actual[item_sel['SKU']]
                    guardar_db(db_actual)
                    st.rerun()

    with st.expander("➕ Alta de Materiales y Asignación Manual"):
        with st.form("new_part_manual"):
            new_sku = st.text_input("Nuevo SKU (Manual)").upper()
            new_name = st.text_input("Descripción")
            
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
                    st.session_state.db[new_sku] = {
                        "nombre": new_name, "peso": p, "cantidad": cant_manual, "volumen": vol, "rack": r, 
                        "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    
                    if generar_qr_fisico:
                        qr_img = qrcode.make(new_sku)
                        qr_img.save(f"label_{new_sku}.png")
                        st.image(f"label_{new_sku}.png", width=200)
                        
                    st.success(f"Registrado en {r} (P{piso}-F{fila}-C{columna}).")
