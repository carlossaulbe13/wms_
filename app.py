import streamlit as st
import paho.mqtt.client as mqtt
import json
import requests
import pandas as pd
import qrcode
import plotly.graph_objects as go
import time
from datetime import datetime
from PIL import Image

# --- CONFIGURACIÓN DE NUBE Y MQTT (DATOS ORIGINALES) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC_PUB = "almacen/escaneo"

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="UMAD Warehouse System", layout="wide")

# --- INICIALIZACIÓN DE ESTADOS ---
if 'vista' not in st.session_state:
    st.session_state.vista = "PLANTA" # PLANTA, ELEVACION, SOBREDIMENSIONES
if 'fila_sel' not in st.session_state:
    st.session_state.fila_sel = None

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def guardar_db(db):
    requests.put(FIREBASE_URL, json=db)

# --- VISTA 1: PLANTA (13m x 37m) ---
def dibujar_planta_limpia():
    fig = go.Figure()
    # Nave
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=37, line=dict(color="Black", width=3))
    # Zonas
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=7, fillcolor="LightSteelBlue", opacity=0.3, line_width=0)
    fig.add_shape(type="rect", x0=0, y0=7, x1=13, y1=17, fillcolor="NavajoWhite", opacity=0.3, line_width=0)
    fig.add_shape(type="rect", x0=0, y0=33, x1=13, y1=37, fillcolor="PaleGreen", opacity=0.3, line_width=0)
    
    # Racks (Zonas de clic lógicas)
    fig.add_shape(type="rect", x0=0, y0=17, x1=1.05, y1=32.5, fillcolor="DarkSlateBlue") # Fila A
    fig.add_shape(type="rect", x0=5.05, y0=17, x1=7.15, y1=32.5, fillcolor="DarkSlateBlue") # Filas B/C
    fig.add_shape(type="rect", x0=11.15, y0=12.2, x1=12.2, y1=32.5, fillcolor="DarkSlateBlue") # Fila D

    fig.update_layout(xaxis=dict(range=[-1, 14], showgrid=False, zeroline=False),
                      yaxis=dict(range=[-1, 38], showgrid=False, zeroline=False),
                      plot_bgcolor='white', width=400, height=700, showlegend=False)
    return fig

# --- VISTA 2: ELEVACIÓN FRONTAL (RACKS 3m) ---
def mostrar_elevacion(fila):
    st.subheader(f"Vista Frontal: Fila {fila} (Racks de 3m)")
    db = cargar_db()
    
    for nivel in [3, 2, 1]:
        st.write(f"**Nivel {nivel}**")
        cols = st.columns(5) # 5 Secciones
        for sec in range(5):
            with cols[sec]:
                st.caption(f"Sec {sec+1}")
                p1, p2, p3 = st.columns(3)
                for i, p in enumerate([p1, p2, p3]):
                    pos_id = f"{fila}-{sec+1}-{nivel}-{i+1}"
                    # Buscar si está ocupado en DB
                    item = next((v for v in db.values() if v.get('fila')==fila and v.get('seccion')==sec+1 and v.get('nivel')==nivel and v.get('posicion')==i+1), None)
                    
                    if item:
                        p.button("📦", key=pos_id, help=f"{item['nombre']} ({item['peso']}kg)")
                    else:
                        p.button("⚪", key=pos_id, help="Espacio Libre")

# --- INTERFAZ PRINCIPAL ---
st.title("🛡️ UMAD Warehouse System")
menu = st.sidebar.radio("Navegación", ["Monitoreo y Ubicación", "Registro de Entrada", "Salida"])

if menu == "Monitoreo y Ubicación":
    if st.session_state.vista == "PLANTA":
        col1, col2 = st.columns([1.2, 1])
        with col1:
            st.plotly_chart(dibujar_planta_limpia())
        with col2:
            st.write("### Control de Navegación")
            if st.button("🔍 Inspeccionar Racks (Vista Frontal)"):
                st.session_state.vista = "ELEVACION"
                st.rerun()
            if st.button("🚜 Inspeccionar Sobredimensiones (Piso)"):
                st.session_state.vista = "SOBREDIMENSIONES"
                st.rerun()
            
    elif st.session_state.vista == "ELEVACION":
        if st.button("⬅️ Volver a Planta"):
            st.session_state.vista = "PLANTA"
            st.rerun()
        fila = st.selectbox("Seleccione Fila:", ["A", "B", "C", "D"])
        mostrar_elevacion(fila)

    elif st.session_state.vista == "SOBREDIMENSIONES":
        if st.button("⬅️ Volver a Planta"):
            st.session_state.vista = "PLANTA"
            st.rerun()
        st.write("### Mapa de Piso (Tinas y Tambos)")
        # Lógica de cuadrícula simple para el suelo...
        st.info("Mostrando slots disponibles en zona naranja (7m-17m)")

# --- MÓDULO DE REGISTRO (LOGICA ORIGINAL ADAPTADA) ---
elif menu == "Registro de Entrada":
    st.header("📥 Registro de Material")
    with st.form("entrada"):
        nombre = st.text_input("Material")
        tipo = st.selectbox("Contenedor", ["Pallet", "Tina LAMTEC", "Tambo"])
        peso = st.number_input("Peso (kg)", min_value=1)
        if st.form_submit_button("Asignar y Notificar"):
            # Aquí va tu lógica de búsqueda y el MQTT publish...
            st.success("Buscando mejor ubicación...")
