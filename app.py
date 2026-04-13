import streamlit as st
import paho.mqtt.client as mqtt
import requests
import pandas as pd
import plotly.graph_objects as go
import qrcode
import time
from datetime import datetime

# --- CONFIGURACION NUBE Y MQTT (TUS CREDENCIALES) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC_PUB = "almacen/escaneo"

# --- INICIALIZACIÓN DE ESTADOS DE NAVEGACIÓN ---
if 'vista' not in st.session_state:
    st.session_state.vista = "PLANTA_GENERAL"
if 'zona_activa' not in st.session_state:
    st.session_state.zona_activa = None

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def guardar_db(db):
    requests.put(FIREBASE_URL, json=db)

# --- CONSTRUCCIÓN DEL MAPA (IGUAL AL CROQUIS) ---
def generar_mapa_2D():
    fig = go.Figure()
    # 1. Contorno Almacén (13m x 37m)
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=37, line=dict(color="Black", width=4))

    # 2. Zona Recepción (Abajo - Y: 0-7)
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=7, fillcolor="LightSteelBlue", opacity=0.4, line_width=0)
    fig.add_annotation(x=6.5, y=3.5, text="RECEPCIÓN", showarrow=False, font=dict(size=14))

    # 3. Zona Sobredimensiones (Centro - Y: 7-17)
    # Bloques laterales según tu dibujo
    fig.add_shape(type="rect", x0=0, y0=7, x1=4, y1=17, fillcolor="NavajoWhite", opacity=0.6, line_width=2)
    fig.add_shape(type="rect", x0=9, y0=7, x1=13, y1=17, fillcolor="NavajoWhite", opacity=0.6, line_width=2)
    fig.add_annotation(x=6.5, y=12, text="SOBREDIMENSIONES", showarrow=False)

    # 4. Zona de Almacén / Racks (Arriba - Y: 17-33)
    # Racks laterales sombreados como en tu croquis
    fig.add_shape(type="rect", x0=0, y0=17, x1=2, y1=33, fillcolor="DarkSlateBlue", opacity=0.8)
    fig.add_shape(type="rect", x0=11, y0=17, x1=13, y1=33, fillcolor="DarkSlateBlue", opacity=0.8)
    fig.add_annotation(x=6.5, y=25, text="ZONA DE ALMACÉN (RACKS)", showarrow=False)

    # 5. Maniobra de Retorno (Fondo - Y: 33-37)
    fig.add_shape(type="rect", x0=0, y0=33, x1=13, y1=37, fillcolor="PaleGreen", opacity=0.4)
    fig.add_annotation(x=6.5, y=35, text="RETORNO", showarrow=False)

    # Pasillo Central (Resaltado amarillo como tu croquis)
    fig.add_shape(type="line", x0=4.5, y0=0, x1=4.5, y1=37, line=dict(color="Yellow", width=2, dash="dash"))
    fig.add_shape(type="line", x0=8.5, y0=0, x1=8.5, y1=37, line=dict(color="Yellow", width=2, dash="dash"))

    fig.update_layout(
        xaxis=dict(range=[-1, 14], visible=False),
        yaxis=dict(range=[-1, 38], visible=False),
        plot_bgcolor='white', width=450, height=850, margin=dict(l=0,r=0,t=0,b=0)
    )
    return fig

# --- VISTA DETALLE: ELEVACIÓN DE RACKS ---
def render_elevacion_racks(fila):
    st.header(f"🏗️ Vista Frontal: Rack Fila {fila}")
    db = cargar_db()
    # 5 Secciones de 3m, 3 Niveles, 3 Posiciones por nivel
    for nivel in [3, 2, 1]:
        st.write(f"**Nivel {nivel}**")
        secciones = st.columns(5)
        for s in range(5):
            with secciones[s]:
                st.caption(f"S{s+1}")
                p1, p2, p3 = st.columns(3)
                for i, p_col in enumerate([p1, p2, p3]):
                    loc_id = f"{fila}-{s+1}-{nivel}-{i+1}"
                    item = next((v for v in db.values() if v.get('ubicacion') == loc_id), None)
                    if item:
                        p_col.button("📦", key=loc_id, help=f"{item['nombre']} | {item['peso']}kg")
                    else:
                        p_col.button("⚪", key=loc_id)

# --- APP PRINCIPAL ---
st.set_page_config(page_title="UMAD Digital Twin", layout="wide")
st.title("🛡️ UMAD Warehouse Management System")

menu = st.sidebar.radio("Navegación", ["Monitoreo Interactivos", "Entradas", "Inventario"])

if menu == "Monitoreo Interactivos":
    if st.session_state.vista == "PLANTA_GENERAL":
        col1, col2 = st.columns([1, 1])
        with col1:
            st.plotly_chart(generar_mapa_2D(), use_container_width=True)
        with col2:
            st.write("### 🎮 Navegador del Gemelo Digital")
            st.info("Selecciona el área que deseas inspeccionar:")
            if st.button("🔍 Ver Niveles de RACK IZQUIERDO (Fila A)"):
                st.session_state.vista = "ELEVACION"; st.session_state.zona_activa = "A"; st.rerun()
            if st.button("🔍 Ver Niveles de RACK DERECHO (Fila B)"):
                st.session_state.vista = "ELEVACION"; st.session_state.zona_activa = "B"; st.rerun()
            if st.button("🚜 Gestionar Zona SOBREDIMENSIONES"):
                st.session_state.vista = "PISO"; st.rerun()

    elif st.session_state.vista == "ELEVACION":
        if st.button("⬅️ VOLVER AL MAPA GENERAL"):
            st.session_state.vista = "PLANTA_GENERAL"; st.rerun()
        render_elevacion_racks(st.session_state.zona_activa)

elif menu == "Entradas":
    st.header("📥 Registro de Material")
    # Formulario de registro...
