import streamlit as st
import paho.mqtt.client as mqtt
import requests
import json
import qrcode
import time
from datetime import datetime

# --- CONFIGURACIÓN DE NUBE Y MQTT (TUS DATOS) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"

# --- INICIALIZACIÓN DE ESTADO DE NAVEGACIÓN ---
if 'vista' not in st.session_state:
    st.session_state.vista = "PLANTA"  # PLANTA, RACKS, SOBREDIMENSIONES
if 'fila_sel' not in st.session_state:
    st.session_state.fila_sel = "A"

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except: return {}

def guardar_db(db):
    requests.put(FIREBASE_URL, json=db)

# --- 1. VISTA DE PLANTA (ZONAS DESPLEGABLES) ---
def render_planta_general():
    st.info("📍 Seleccione un área operativa para desplegar el detalle")
    
    # Representación visual por bloques (Frente 13m x Largo 37m)
    # 1. Recepción (Informativa)
    st.button("🟦 RECEPCIÓN (0m - 7m)", use_container_width=True, disabled=True)
    
    # 2. Sobredimensiones (Interactiva)
    if st.button("🟧 ZONA SOBREDIMENSIONES: TINAS Y TAMBOS (7m - 17m)", use_container_width=True):
        st.session_state.vista = "SOBREDIMENSIONES"
        st.rerun()
    
    # 3. Almacenaje de Racks (Interactiva)
    if st.button("🗄️ ZONA DE ALMACENAJE: RACKS SELECTIVOS (17m - 33m)", use_container_width=True):
        st.session_state.vista = "RACKS"
        st.rerun()
        
    # 4. Retorno (Informativa)
    st.button("🟩 MANIOBRA DE RETORNO (33m - 37m)", use_container_width=True, disabled=True)

# --- 2. VISTA DE ELEVACIÓN (DRILL-DOWN RACKS) ---
def render_frontal_racks():
    st.header(f"🏗️ Vista Frontal: Fila {st.session_state.fila_sel}")
    if st.button("⬅️ Volver a Mapa de Planta"):
        st.session_state.vista = "PLANTA"
        st.rerun()

    # Selector de Fila
    filas = ["A", "B", "C", "D"]
    st.session_state.fila_sel = st.pills("Seleccionar Fila:", filas, default=st.session_state.fila_sel)
    
    db = cargar_db()
    
    # Estructura: 3 Niveles de altura
    for nivel in [3, 2, 1]:
        st.write(f"#### NIVEL {nivel}")
        secciones = st.columns(5) # 5 Secciones de 3 metros
        for s in range(5):
            with secciones[s]:
                st.caption(f"Secc. {s+1}")
                # 3 Posiciones por cada viga de 3m
                p1, p2, p3 = st.columns(3)
                for i, col_pos in enumerate([p1, p2, p3]):
                    # ID de ubicación técnica: Fila-Seccion-Nivel-Posicion
                    loc_id = f"{st.session_state.fila_sel}-{s+1}-{nivel}-{i+1}"
                    
                    # Buscar si hay material
                    item = next((v for v in db.values() if v.get('fila')==st.session_state.fila_sel 
                                 and v.get('seccion')==s+1 and v.get('nivel')==nivel 
                                 and v.get('posicion')==i+1), None)
                    
                    if item:
                        if col_pos.button("📦", key=loc_id, help=f"{item['nombre']} ({item['peso']}kg)"):
                            st.toast(f"Detalle: {item['nombre']} | Peso: {item['peso']}kg | Registrado: {item.get('fecha','')}")
                    else:
                        col_pos.button("⚪", key=loc_id, help="Espacio Disponible")

# --- 3. VISTA SOBREDIMENSIONES (DRILL-DOWN PISO) ---
def render_piso_sobredimensiones():
    st.header("🚜 Zona de Sobredimensiones (Piso)")
    if st.button("⬅️ Volver a Mapa de Planta"):
        st.session_state.vista = "PLANTA"
        st.rerun()
    
    st.write("Layout de estiba directa (Tinas LAMTEC y Tambos)")
    # Aquí se genera una cuadrícula de 10m x 13m (simplificada a botones)
    for r in range(1, 4):
        cols = st.columns(5)
        for c in range(5):
            cols[c].button(f"Slot {r}-{c+1}", key=f"PISO_{r}_{c}")

# --- APP PRINCIPAL ---
st.title("🛡️ UMAD Warehouse System")
st.sidebar.title("Navegación")
modo = st.sidebar.radio("Módulo", ["Monitoreo", "Entradas", "Salidas"])

if modo == "Monitoreo":
    if st.session_state.vista == "PLANTA":
        render_planta_general()
    elif st.session_state.vista == "RACKS":
        render_frontal_racks()
    elif st.session_state.vista == "SOBREDIMENSIONES":
        render_piso_sobredimensiones()

elif modo == "Entradas":
    st.header("📥 Registro de Material")
    # Tu lógica original de formulario aquí conectada a cargar_db() y guardar_db()
    st.info("Módulo de registro vinculado a la nueva matriz de 180 posiciones.")
