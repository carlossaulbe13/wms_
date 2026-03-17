import streamlit as st
import paho.mqtt.client as mqtt
import json
import os
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import qrcode
from PIL import Image

# --- ARCHIVO DE BASE DE DATOS LOCAL ---
DB_FILE = "maestro_articulos.json"

def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

if 'db' not in st.session_state:
    st.session_state.db = cargar_db()

# --- CONFIGURACIÓN MQTT ---
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC = "almacen/escaneo"

# Inicializar cliente MQTT
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set() 
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()
        st.session_state.mqtt_client = client
        st.session_state.mqtt_connected = True
    except Exception as e:
        st.session_state.mqtt_connected = False
        st.error(f"Error de conexión MQTT: {e}")

# --- INTERFAZ DE USUARIO ---
st.set_page_config(page_title="WMS Nave de Pintura", layout="wide")
st.title("🖌️ Gestión de Almacén - Nave de Pintura")

# Panel lateral
with st.sidebar:
    st.header("Estado del Sistema")
    if st.session_state.get('mqtt_connected'):
        st.success("🟢 Conectado a HiveMQ")
    else:
        st.error("🔴 Desconectado")
    st.write(f"Artículos en BD: {len(st.session_state.db)}")

# --- LÓGICA DE ESCANEO ---
st.header("📦 Entrada de Material")

tab1, tab2 = st.tabs(["📷 Escanear con Cámara", "⌨️ Ingreso Manual"])
sku = "" 

with tab1:
    st.info("Apunta la cámara de la tablet al código QR del pallet.")
    foto = st.camera_input("Capturar QR")
    
    if foto is not None:
        file_bytes = np.asarray(bytearray(foto.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        qrs = decode(img)
        
        if qrs:
            sku = qrs[0].data.decode('utf-8').strip().upper()
            st.success(f"¡QR Detectado con éxito!: {sku}")
        else:
            st.error("No se detectó ningún código QR. Intenta de nuevo.")

with tab2:
    sku_manual = st.text_input("Ingresar Número de Parte (SKU) a mano").strip().upper()
    if sku_manual:
        sku = sku_manual

# --- LÓGICA DE ASIGNACIÓN ---
if sku:
    st.divider()
    if sku in st.session_state.db:
        # --- MATERIAL CONOCIDO ---
        item = st.session_state.db[sku]
        st.success(f"Material Encontrado: **{item['nombre']}**")
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"- **Peso:** {item['peso']} kg")
            st.write(f"- **Volumen:** {item['volumen']} m³")
        with col2:
            st.info(f"Ubicación Asignada: **{item['rack']}**")
            if st.button(f"Enviar orden al ESP32 ({item['rack']})", use_container_width=True):
                st.session_state.mqtt_client.publish(TOPIC, item['rack'])
                st.toast(f"Comando {item['rack']} enviado a la placa.", icon="✅")
    
    else:
        # --- MATERIAL NUEVO ---
        st.warning(f"El código '{sku}' es nuevo. Regístralo en el sistema:")
        
        with st.form("registro_form"):
            nombre = st.text_input("Descripción del pallet/material")
            
            st.write("Dimensiones y Peso")
            col_p, col_l, col_a, col_h = st.columns(4)
            with col_p:
                peso = st.number_input("Peso (kg)", min_value=0.0, step=1.0)
            with col_l:
                largo = st.number_input("Largo (cm)", min_value=0.0, step=10.0)
            with col_a:
                ancho = st.number_input("Ancho (cm)", min_value=0.0, step=10.0)
            with col_h:
                alto = st.number_input("Alto (cm)", min_value=0.0, step=10.0)
            
            submit = st.form_submit_button("Dar de alta y Asignar")
            
            if submit and nombre:
                # 1. Calcular volumen en m3
                volumen_m3 = (largo / 100) * (ancho / 100) * (alto / 100)
                
                # 2. Lógica de asignación
                if peso >= 200 or volumen_m3 > 2.0:
                    target_rack = "POS_4"
                elif peso >= 50 or volumen_m3 > 1.0:
                    target_rack = "POS_3"
                elif volumen_m3 < 0.5 and peso < 20:
                    target_rack = "POS_1"
                else:
                    target_rack = "POS_2"
                    
                # 3. Guardar en Base de Datos
                st.session_state.db[sku] = {
                    "nombre": nombre,
                    "peso": round(peso, 2),
                    "volumen": round(volumen_m3, 3),
                    "rack": target_rack
                }
                guardar_db(st.session_state.db)
                
                # 4. Generar etiqueta QR física
                qr_img = qrcode.make(sku)
                filename = f"label_{sku}.png"
                qr_img.save(filename)
                
                # 5. Publicar a HiveMQ
                st.session_state.mqtt_client.publish(TOPIC, target_rack)
                
                # 6. Mostrar retroalimentación
                st.success(f"Registrado exitosamente. Asignado a **{target_rack}**.")
                st.toast(f"Comando {target_rack} enviado al ESP32.", icon="🚀")
                
                # 7. Mostrar la etiqueta generada
                st.header("🖨️ Etiqueta QR Generada")
                st.info(f"Imprime esta etiqueta y pégala en el pallet '{sku}'.")
                st.image(filename, width=250)