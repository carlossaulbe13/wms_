import streamlit as st
import paho.mqtt.client as mqtt
import json
import os
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import qrcode
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

# --- CONFIGURACIÓN DE ARCHIVOS Y RED ---
DB_FILE = "maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC = "almacen/escaneo"

# --- FUNCIONES DE PERSISTENCIA ---
def cargar_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def guardar_db(db):
    with open(DB_FILE, 'w') as f:
        json.dump(db, f, indent=4)

# Inicializar Base de Datos en la sesión
if 'db' not in st.session_state:
    st.session_state.db = cargar_db()

# --- CONEXIÓN MQTT ---
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()
    st.session_state.mqtt_client = client

# --- INTERFAZ ---
st.set_page_config(page_title="VEX Paint Shop WMS", layout="wide")

# Título con estilo industrial
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>🏗️ VEX Central Control - Nave de Pintura</h1>", unsafe_allow_html=True)

tabs = st.tabs(["📊 Monitor y Croquis", "📷 Escáner de Campo", "📁 Maestro de Artículos"])

# --- PESTAÑA 1: MONITOR Y CROQUIS ---
with tabs[0]:
    st.header("Mapa en Tiempo Real de la Nave")
    
    # Dibujamos los Racks como columnas
    col_map = st.columns(5)
    racks_visual = ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"]
    
    for i, rack_id in enumerate(racks_visual):
        with col_map[i]:
            # Filtrar materiales en este rack
            materiales_aqui = [v['nombre'] for k, v in st.session_state.db.items() if v.get('rack') == rack_id and v.get('estado') != "CONGELADO"]
            
            color = "#28a745" if materiales_aqui else "#6c757d"
            st.markdown(f"""
                <div style="background-color: {color}; padding: 20px; border-radius: 10px; text-align: center; color: white;">
                    <h3>Rack {i+1}</h3>
                    <p>{len(materiales_aqui)} Items</p>
                </div>
            """, unsafe_allow_html=True)
            
            for m in materiales_aqui:
                st.caption(f"📦 {m}")

# --- PESTAÑA 2: ESCÁNER DE CAMPO ---
with tabs[1]:
    st.subheader("Captura de Material (Uso en Celular/Tablet)")
    foto = st.camera_input("Escanear QR del Pallet")
    
    sku_detectado = ""
    if foto:
        file_bytes = np.asarray(bytearray(foto.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        qrs = decode(img)
        if qrs:
            sku_detectado = qrs[0].data.decode('utf-8').strip().upper()
            
            if sku_detectado in st.session_state.db:
                item = st.session_state.db[sku_detectado]
                if item.get('estado') == "CONGELADO":
                    st.error(f"⚠️ EL MATERIAL {sku_detectado} ESTÁ CONGELADO. NO MOVER.")
                else:
                    st.success(f"Asignando {item['nombre']} a {item['rack']}")
                    st.session_state.mqtt_client.publish(TOPIC, item['rack'])
            else:
                st.warning("Material nuevo detectado. Regístralo en la pestaña 'Maestro'.")

# --- PESTAÑA 3: MAESTRO DE ARTÍCULOS (CRUD) ---
with tabs[2]:
    st.header("Gestión del Inventario (SAP B1 Style)")
    
    # Convertir DB a lista para la tabla
    data_tabla = []
    for k, v in st.session_state.db.items():
        data_tabla.append({"SKU": k, **v})
    
    if data_tabla:
        gb = GridOptionsBuilder.from_dataframe(np.array(data_tabla)) # Simplificado para el ejemplo
        gb.configure_selection('single', use_checkbox=True)
        gridOptions = gb.build()
        
        st.write("Selecciona un material para editar o congelar:")
        grid_response = AgGrid(
            data_tabla, 
            gridOptions=gridOptions,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme='streamlit'
        )
        
        selected = grid_response['selected_rows']
        
        if selected:
            sel = selected[0]
            st.divider()
            col_ed1, col_ed2 = st.columns(2)
            
            with col_ed1:
                nuevo_nombre = st.text_input("Nombre", value=sel['nombre'])
                nuevo_estado = st.selectbox("Estado", ["ACTIVO", "CONGELADO"], index=0 if sel.get('estado')=="ACTIVO" else 1)
            
            with col_ed2:
                if st.button("Guardar Cambios"):
                    st.session_state.db[sel['SKU']]['nombre'] = nuevo_nombre
                    st.session_state.db[sel['SKU']]['estado'] = nuevo_estado
                    guardar_db(st.session_state.db)
                    st.success("Cambios guardados. Refrescando...")
                    st.rerun()
                
                if st.button("🗑️ Eliminar Definitivamente"):
                    del st.session_state.db[sel['SKU']]
                    guardar_db(st.session_state.db)
                    st.rerun()

    # Formulario para NUEVOS materiales (abajo de la tabla)
    with st.expander("➕ Dar de Alta Nuevo Material"):
        with st.form("new_part"):
            new_sku = st.text_input("Nuevo SKU").upper()
            new_name = st.text_input("Descripción")
            c1, c2, c3 = st.columns(3)
            with c1: p = st.number_input("Peso (kg)")
            with c2: v = st.number_input("Volumen (m3)")
            with c3: r = st.selectbox("Rack Sugerido", ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"])
            
            if st.form_submit_button("Registrar y Generar QR"):
                st.session_state.db[new_sku] = {"nombre": new_name, "peso": p, "volumen": v, "rack": r, "estado": "ACTIVO"}
                guardar_db(st.session_state.db)
                qr_img = qrcode.make(new_sku)
                qr_img.save(f"label_{new_sku}.png")
                st.image(f"label_{new_sku}.png", width=200)
                st.success("Registrado.")
