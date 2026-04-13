import streamlit as st
import paho.mqtt.client as mqtt
import requests
import pandas as pd
import plotly.graph_objects as go
import qrcode
from datetime import datetime
import time

# --- CONFIGURACIÓN DE NUBE Y MQTT ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC_PUB = "almacen/escaneo"

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="UMAD WMS - Digital Twin", layout="wide")

# --- CONTROL DE ESTADO DE NAVEGACIÓN ---
if 'vista' not in st.session_state:
    st.session_state.vista = "PLANTA"  # PLANTA, RACKS, SOBREDIMENSIONES
if 'fila_activa' not in st.session_state:
    st.session_state.fila_activa = "A"

# --- FUNCIONES CORE ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def guardar_db(db):
    requests.put(FIREBASE_URL, json=db)

# --- VISTA DE PLANTA (INTERACTIVA) ---
def dibujar_planta_interactiva():
    fig = go.Figure()
    # Nave 13x37
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=37, line=dict(color="Black", width=3))
    # Zonas coloreadas
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=7, fillcolor="LightSteelBlue", opacity=0.3, line_width=0)
    fig.add_shape(type="rect", x0=0, y0=7, x1=13, y1=17, fillcolor="NavajoWhite", opacity=0.3, line_width=0)
    fig.add_shape(type="rect", x0=0, y0=33, x1=13, y1=37, fillcolor="PaleGreen", opacity=0.3, line_width=0)
    
    # Racks (Visual)
    racks = [(0, 1.05, "Fila A"), (5.05, 7.15, "Filas B/C"), (11.15, 12.2, "Fila D")]
    for rx in racks:
        fig.add_shape(type="rect", x0=rx[0], y0=17, x1=rx[1], y1=32.5, fillcolor="DarkSlateBlue")

    fig.update_layout(xaxis=dict(range=[-1, 14], showgrid=False, zeroline=False),
                      yaxis=dict(range=[-1, 38], showgrid=False, zeroline=False),
                      plot_bgcolor='white', height=750, showlegend=False, margin=dict(l=0,r=0,t=0,b=0))
    return fig

# --- VISTA DE ELEVACIÓN (FRONTAL) ---
def vista_frontal_racks(fila):
    st.markdown(f"### 🏗️ Inspección Frontal: FILA {fila}")
    db = cargar_db()
    
    # Cada viga de 3m tiene 3 posiciones
    for nivel in [3, 2, 1]:
        st.write(f"**Nivel {nivel}**")
        secciones = st.columns(5) # 5 Secciones por largo
        for s in range(5):
            with secciones[s]:
                st.caption(f"Secc. {s+1}")
                p1, p2, p3 = st.columns(3)
                for i, p_col in enumerate([p1, p2, p3]):
                    pos_id = f"{fila}-{s+1}-{nivel}-{i+1}"
                    # Buscar item en DB
                    item = next((v for v in db.values() if v.get('fila')==fila and v.get('seccion')==s+1 
                                 and v.get('nivel')==nivel and v.get('posicion')==i+1), None)
                    
                    if item:
                        if p_col.button("📦", key=pos_id):
                            st.toast(f"Contenido: {item['nombre']} | Peso: {item['peso']}kg")
                    else:
                        p_col.button("⚪", key=pos_id)

# --- NAVEGACIÓN PRINCIPAL ---
st.sidebar.title("UMAD WMS")
app_mode = st.sidebar.radio("Módulo", ["Monitoreo", "Entradas", "Inventario"])

if app_mode == "Monitoreo":
    if st.session_state.vista == "PLANTA":
        col_map, col_nav = st.columns([1.5, 1])
        with col_map:
            st.plotly_chart(dibujar_planta_interactiva(), use_container_width=True)
        with col_nav:
            st.write("### Panel de Navegación")
            st.info("Haga clic en el área que desea desplegar:")
            if st.button("🔍 DESPLEGAR ZONA DE RACKS (ELEVACIÓN)"):
                st.session_state.vista = "RACKS"
                st.rerun()
            if st.button("🚜 DESPLEGAR SOBREDIMENSIONES (PISO)"):
                st.session_state.vista = "SOBREDIMENSIONES"
                st.rerun()

    elif st.session_state.vista == "RACKS":
        if st.button("⬅️ VOLVER A PLANTA GENERAL"):
            st.session_state.vista = "PLANTA"
            st.rerun()
        
        fila_sel = st.segmented_control("Seleccionar Fila para Inspección:", ["A", "B", "C", "D"], default="A")
        vista_frontal_racks(fila_sel)

    elif st.session_state.vista == "SOBREDIMENSIONES":
        if st.button("⬅️ VOLVER A PLANTA GENERAL"):
            st.session_state.vista = "PLANTA"
            st.rerun()
        st.write("### 📍 Mapa de Piso: Zona de Tinas y Tambos")
        # Aquí dibujarías una cuadrícula simple de 10x13 slots...
