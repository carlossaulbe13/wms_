import streamlit as st
import paho.mqtt.client as mqtt
import requests
import pandas as pd
import plotly.graph_objects as go
import qrcode
import time
from datetime import datetime

# --- CONFIGURACION NUBE Y MQTT (TUS DATOS) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"

# --- INICIALIZACIÓN DE ESTADO ---
if 'vista' not in st.session_state:
    st.session_state.vista = "PLANTA"
if 'seccion_detalle' not in st.session_state:
    st.session_state.seccion_detalle = None

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

# --- CSS PERSONALIZADO (ESTILO DASHBOARD PRO) ---
st.markdown("""
    <style>
    .zone-box {
        border-radius: 10px; padding: 20px; text-align: center; color: white;
        font-weight: bold; border: 1px solid rgba(255,255,255,0.1); margin-bottom: 10px;
    }
    .recepcion { background-color: #2c2c3e; }
    .sobredimensiones { background-color: #5d4a26; }
    .almacenaje { background-color: #1a1a1a; border: 2px solid #3e3e4e; }
    .retorno { background-color: #2c2c3e; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. VISTA PLANTA GENERAL (GEMELO DIGITAL) ---
def render_planta():
    st.markdown("### 🌐 Gemelo Digital: Vista de Planta")
    
    # Usamos columnas para representar el flujo longitudinal (como tu mock-up)
    # 13m ancho x 37m largo
    c1, c2, c3, c4 = st.columns([1, 1.5, 3, 0.8])
    
    with c1:
        st.markdown('<div class="zone-box recepcion">🚛<br>RECEPCIÓN</div>', unsafe_allow_html=True)
    
    with c2:
        if st.button("📦 SOBREDIMENSIONES", use_container_width=True):
            st.session_state.vista = "DETALLE_PISO"
            st.rerun()
        st.markdown('<div style="height:100px; background-color:#5d4a26; border-radius:5px; opacity:0.5;"></div>', unsafe_allow_html=True)
        
    with c3:
        st.markdown('<div style="text-align:center; color:#888;">ALMACENAJE</div>', unsafe_allow_html=True)
        for fila in ["A", "B", "C", "D"]:
            if st.button(f"Fila {fila}", key=f"btn_{fila}", use_container_width=True):
                st.session_state.seccion_detalle = fila
                st.session_state.vista = "DETALLE_RACK"
                st.rerun()
                
    with c4:
        st.markdown('<div class="zone-box retorno">🔄<br>RETORNO</div>', unsafe_allow_html=True)

# --- 2. VISTA DETALLE: ELEVACIÓN DE RACKS (DRILL-DOWN) ---
def render_detalle_rack(fila):
    st.header(f"🏗️ Elevación Frontal: FILA {fila}")
    if st.button("⬅️ Volver al Mapa General"):
        st.session_state.vista = "PLANTA"
        st.rerun()
    
    db = cargar_db()
    # 5 Secciones, 3 Niveles, 3 Posiciones (Vigas 3m)
    for nivel in [3, 2, 1]:
        st.write(f"**Nivel {nivel}**")
        secciones = st.columns(5)
        for s in range(5):
            with secciones[s]:
                st.caption(f"Secc {s+1}")
                p1, p2, p3 = st.columns(3)
                for i, p_col in enumerate([p1, p2, p3]):
                    loc_id = f"{fila}-{s+1}-{nivel}-{i+1}"
                    # Verificamos ocupación en Firebase
                    item = next((v for v in db.values() if v.get('rack') == loc_id), None)
                    if item:
                        p_col.button("📦", key=loc_id, help=f"{item['nombre']} | {item['peso']}kg")
                    else:
                        p_col.button("⚪", key=loc_id)

# --- INTERFAZ PRINCIPAL ---
st.set_page_config(page_title="UMAD WMS Twin", layout="wide")
st.title("🛡️ UMAD Warehouse System")

menu = st.sidebar.radio("Navegación", ["Monitoreo", "Entradas", "Salidas"])

if menu == "Monitoreo":
    if st.session_state.vista == "PLANTA":
        render_planta()
    elif st.session_state.vista == "DETALLE_RACK":
        render_detalle_rack(st.session_state.seccion_detalle)

elif menu == "Entradas":
    st.header("📥 Registro de Material")
    # Tu lógica de registro original aquí...
