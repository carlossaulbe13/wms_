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
# He añadido el ".json" al final de tu URL, es obligatorio para que funcione con Python
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"

def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception as e:
        st.error(f"Error de conexión con la nube: {e}")
    return {}

def guardar_db(db):
    try:
        requests.put(FIREBASE_URL, json=db)
    except Exception as e:
        st.error(f"Error al guardar en la nube: {e}")

# --- CONFIGURACIÓN MQTT ---
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC = "almacen/escaneo"

# --- LÓGICA DE ASIGNACIÓN ---
def obtener_coordenada_libre(db, rack_objetivo):
    # Buscamos coordenadas ya ocupadas en este rack
    ocupadas = [(v.get('piso'), v.get('fila'), v.get('columna')) for v in db.values() if v.get('rack') == rack_objetivo]
    for p in range(1, 6): # 5 Pisos
        for f in range(1, 4): # 3 Filas
            for c in range(1, 5): # 4 Columnas
                if (p, f, c) not in ocupadas:
                    return p, f, c
    return None, None, None

# Inicialización de estados
if 'db' not in st.session_state:
    st.session_state.db = cargar_db()
if 'sku_pendiente' not in st.session_state:
    st.session_state.sku_pendiente = None

# --- INTERFAZ ---
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>UMAD Warehouse Management System</h1>", unsafe_allow_html=True)

tabs = st.tabs(["Monitoreo y Ubicación", "Escáner de Campo", "Maestro de Artículos"])

# --- PESTAÑA 1: MONITOR (TIEMPO REAL) ---
with tabs[0]:
    # Refrescar automáticamente cada 3 segundos para ver cambios del celular
    st_autorefresh(interval=3000, key="datarefresh")
    st.session_state.db = cargar_db() # Recargar datos de Firebase

    st.header("Mapa de Racks en Tiempo Real")
    col1, col2 = st.columns(2)
    with col1:
        r_sel = st.selectbox("Rack:", ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"])
    with col2:
        p_sel = st.selectbox("Piso:", [1, 2, 3, 4, 5])

    st.subheader(f"Estado de {r_sel} - Nivel {p_sel}")
    
    for fila in range(1, 4):
        cols = st.columns(4)
        for col in range(1, 5):
            # Buscar si hay algo en esta coordenada
            item = next((v for v in st.session_state.db.values() if v.get('rack')==r_sel and v.get('piso')==p_sel and v.get('fila')==fila and v.get('columna')==col), None)
            
            with cols[col-1]:
                if item:
                    # Lógica de colores Saúl: Amarillo (Ocupado), Rojo (Congelado)
                    es_congelado = item.get('estado') == "CONGELADO"
                    bg = "#f8d7da" if es_congelado else "#fff3cd"
                    border = "#dc3545" if es_congelado else "#ffc107"
                    label = "⚠️ CONGELADO" if es_congelado else "📦 OCUPADO"
                    
                    st.markdown(f"""
                        <div style='background-color:{bg}; border:3px solid {border}; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'>
                            <b style='font-size:14px;'>{item['nombre']}</b><br>
                            <span style='font-size:12px;'>{label}</span><br>
                            <small>F{fila}-C{col}</small>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    # Verde: Disponible
                    st.markdown(f"""
                        <div style='background-color:#d4edda; border:3px solid #28a745; border-radius:10px; padding:10px; text-align:center; color:black; min-height:100px;'>
                            <b style='font-size:14px;'>DISPONIBLE</b><br>
                            <span style='font-size:12px;'>Libre</span><br>
                            <small>F{fila}-C{col}</small>
                        </div>
                    """, unsafe_allow_html=True)

# --- PESTAÑA 2: ESCÁNER ---
with tabs[1]:
    if st.session_state.sku_pendiente is None:
        foto = st.camera_input("Escanear Código de Material")
        if foto:
            img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
            codes = decode(img)
            if codes:
                sku = codes[0].data.decode('utf-8').upper()
                if sku in st.session_state.db:
                    info = st.session_state.db[sku]
                    st.success(f"Material identificado: {info['nombre']} en {info['rack']}")
                    # Aquí podrías enviar el MQTT
                else:
                    st.session_state.sku_pendiente = sku
                    st.rerun()
    else:
        st.warning(f"Nuevo QR Detectado: {st.session_state.sku_pendiente}")
        with st.form("registro_nube"):
            nom = st.text_input("Nombre del Material")
            peso = st.number_input("Peso (kg)", 0.0)
            l, a, h = st.columns(3)
            with l: la = st.number_input("Largo", 0.0)
            with a: an = st.number_input("Ancho", 0.0)
            with h: al = st.number_input("Alto", 0.0)
            
            if st.form_submit_button("Dar de alta en la Nube"):
                vol = (la*an*al)/1000000
                # Lógica de Rack por peso
                rack = "POS_4" if peso > 100 else "POS_1"
                piso, fila, col = obtener_coordenada_libre(st.session_state.db, rack)
                
                if piso:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "nombre": nom, "peso": peso, "rack": rack, "piso": piso, "fila": fila, "columna": col, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.session_state.sku_pendiente = None
                    st.success("Guardado en Firebase con éxito.")
                    st.rerun()

# --- PESTAÑA 3: MAESTRO ---
with tabs[2]:
    st.header("Inventario Maestro")
    db_actual = cargar_db()
    if db_actual:
        df = pd.DataFrame([{"SKU": k, **v} for k, v in db_actual.items()])
        st.dataframe(df, use_container_width=True)
        
        sku_del = st.selectbox("Selecciona SKU para eliminar/editar:", list(db_actual.keys()))
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("Congelar/Descongelar"):
                estado_actual = db_actual[sku_del].get('estado', 'ACTIVO')
                db_actual[sku_del]['estado'] = "CONGELADO" if estado_actual == "ACTIVO" else "ACTIVO"
                guardar_db(db_actual)
                st.rerun()
        with col_b2:
            if st.button("Eliminar Permanentemente"):
                del db_actual[sku_del]
                guardar_db(db_actual)
                st.rerun()
