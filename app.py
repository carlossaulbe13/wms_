import streamlit as st
import paho.mqtt.client as mqtt
import json
import os
import cv2
import numpy as np
import pandas as pd
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

if 'sku_pendiente' not in st.session_state:
    st.session_state.sku_pendiente = None

# --- ALGORITMO DE AUTO-ASIGNACIÓN ---
def obtener_coordenada_libre(db, rack_objetivo):
    ocupadas = [(v.get('piso'), v.get('fila'), v.get('columna')) for v in db.values() if v.get('rack') == rack_objetivo]
    for p in range(1, 6):
        for f in range(1, 4):
            for c in range(1, 5):
                if (p, f, c) not in ocupadas:
                    return p, f, c
    return None, None, None

# --- CONEXIÓN MQTT ---
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.loop_start()
        st.session_state.mqtt_client = client
    except Exception as e:
        st.error(f"Error MQTT: {e}")

# --- INTERFAZ UMAD ---
st.set_page_config(page_title="UMAD WMS", layout="wide")
st.markdown("<h1 style='text-align: center; color: #FF4B4B;'>UMAD Warehouse Managment System</h1>", unsafe_allow_html=True)

tabs = st.tabs(["Monitoreo y Ubicación", "Escáner de Campo", "Maestro de Artículos"])

# --- PESTAÑA 1: MONITOR Y CROQUIS ---
with tabs[0]:
    st.header("Mapa Matricial de Racks")
    
    col_sel1, col_sel2 = st.columns(2)
    with col_sel1:
        rack_seleccionado = st.selectbox("Visualizar Rack:", ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"])
    with col_sel2:
        piso_seleccionado = st.selectbox("Visualizar Piso:", [1, 2, 3, 4, 5])
        
    st.markdown(f"### Vista de {rack_seleccionado} - Piso {piso_seleccionado}")
    st.write("*(Distribución 3x4)*")
    
    # Dibujar la cuadrícula con Semáforo
    for fila in range(1, 4):
        cols = st.columns(4)
        for columna in range(1, 5):
            material_encontrado = None
            for k, v in st.session_state.db.items():
                if v.get('rack') == rack_seleccionado and v.get('piso', 1) == piso_seleccionado and v.get('fila', 1) == fila and v.get('columna', 1) == columna:
                    material_encontrado = v
                    break
            
            with cols[columna - 1]:
                if material_encontrado:
                    if material_encontrado.get('estado') == "CONGELADO":
                        # ROJO: Material Congelado
                        bg_color = "#f8d7da" 
                        border_color = "#dc3545"
                    else:
                        # AMARILLO: Lugar Ocupado
                        bg_color = "#fff3cd" 
                        border_color = "#ffc107"
                        
                    st.markdown(f"""
                        <div style='background-color: {bg_color}; padding: 15px; border: 2px solid {border_color}; border-radius: 5px; text-align: center; height: 100px; color: black;'>
                            <strong>📦 {material_encontrado['nombre']}</strong><br>
                            <small>{material_encontrado.get('estado', 'ACTIVO')}</small>
                        </div>
                    """, unsafe_allow_html=True)
                else:
                    # VERDE: Lugar Disponible
                    st.markdown(f"""
                        <div style='background-color: #d4edda; padding: 15px; border: 2px solid #28a745; border-radius: 5px; text-align: center; height: 100px; color: black;'>
                            <strong>F{fila}-C{columna}</strong><br>
                            <span>Disponible</span>
                        </div>
                    """, unsafe_allow_html=True)
        st.write("") 

# --- PESTAÑA 2: ESCÁNER DE CAMPO ---
with tabs[1]:
    st.subheader("Captura de Material")
    
    if st.session_state.sku_pendiente is None:
        foto = st.camera_input("Escanea el código QR:")
        
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
                        coord = f"Piso {item.get('piso',1)}, Fila {item.get('fila',1)}, Col {item.get('columna',1)}"
                        st.success(f"Asignando **{item['nombre']}** a **{item['rack']}** ({coord})")
                        st.session_state.mqtt_client.publish(TOPIC, item['rack'])
                else:
                    st.session_state.sku_pendiente = sku_detectado
                    st.rerun()
                    
    if st.session_state.sku_pendiente is not None:
        st.warning(f"QR Nuevo Detectado: **{st.session_state.sku_pendiente}**")
        st.info("Ingresa los datos para registrar este material manteniendo su código original.")
        
        with st.form("registro_rapido"):
            new_name = st.text_input("Descripción del Material")
            c1, c2, c3, c4 = st.columns(4)
            with c1: p = st.number_input("Peso (kg)", min_value=0.0)
            with c2: l = st.number_input("Largo (cm)", min_value=0.0)
            with c3: a = st.number_input("Ancho (cm)", min_value=0.0)
            with c4: h = st.number_input("Alto (cm)", min_value=0.0)
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1: submit = st.form_submit_button("Guardar y Asignar Ubicación")
            with col_btn2: cancelar = st.form_submit_button("Cancelar Escaneo")
                
            if cancelar:
                st.session_state.sku_pendiente = None
                st.rerun()
                
            if submit and new_name:
                vol = (l/100) * (a/100) * (h/100)
                if p >= 200 or vol > 2.0: r = "POS_4"
                elif p >= 50 or vol > 1.0: r = "POS_3"
                elif vol < 0.5 and p < 20: r = "POS_1"
                else: r = "POS_2"
                
                piso, fila, columna = obtener_coordenada_libre(st.session_state.db, r)
                
                if piso is None:
                    st.error(f"El {r} está completamente lleno.")
                else:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "nombre": new_name, "peso": p, "volumen": vol, "rack": r, 
                        "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    st.success(f"Registrado en {r} (P{piso}-F{fila}-C{columna}).")
                    st.session_state.mqtt_client.publish(TOPIC, r)
                    st.session_state.sku_pendiente = None
                    st.rerun()

# --- PESTAÑA 3: MAESTRO DE ARTÍCULOS ---
with tabs[2]:
    st.header("Gestión del Inventario")
    
    data_tabla = []
    for k, v in st.session_state.db.items():
        data_tabla.append({"SKU": k, **v})
    
    if data_tabla:
        df = pd.DataFrame(data_tabla)
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=True)
        gridOptions = gb.build()
        
        grid_response = AgGrid(df, gridOptions=gridOptions, update_mode=GridUpdateMode.SELECTION_CHANGED, theme='streamlit')
        selected = grid_response['selected_rows']
        
        if selected is not None and len(selected) > 0:
            if isinstance(selected, pd.DataFrame): sel = selected.iloc[0].to_dict()
            else: sel = selected[0]
                
            st.divider()
            st.write(f"### Editando: {sel['SKU']}")
            col_ed1, col_ed2 = st.columns(2)
            
            with col_ed1:
                nuevo_nombre = st.text_input("Nombre", value=sel['nombre'])
                nuevo_estado = st.selectbox("Estado", ["ACTIVO", "CONGELADO"], index=0 if sel.get('estado')=="ACTIVO" else 1)
            
            with col_ed2:
                if st.button("Guardar Cambios"):
                    st.session_state.db[sel['SKU']]['nombre'] = nuevo_nombre
                    st.session_state.db[sel['SKU']]['estado'] = nuevo_estado
                    guardar_db(st.session_state.db)
                    st.success("Cambios guardados.")
                    st.rerun()
                if st.button("Eliminar Número de parte."):
                    del st.session_state.db[sel['SKU']]
                    guardar_db(st.session_state.db)
                    st.rerun()

    with st.expander("➕ Alta de Materiales y Asignación Manual."):
        with st.form("new_part"):
            new_sku = st.text_input("Nuevo SKU (Manual)").upper()
            new_name = st.text_input("Descripción")
            
            c1, c2, c3, c4 = st.columns(4)
            with c1: p = st.number_input("Peso (kg)", min_value=0.0)
            with c2: l = st.number_input("Largo (cm)", min_value=0.0)
            with c3: a = st.number_input("Ancho (cm)", min_value=0.0)
            with c4: h = st.number_input("Alto (cm)", min_value=0.0)
            
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
                        "nombre": new_name, "peso": p, "volumen": vol, "rack": r, 
                        "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    
                    if generar_qr_fisico:
                        qr_img = qrcode.make(new_sku)
                        qr_img.save(f"label_{new_sku}.png")
                        st.image(f"label_{new_sku}.png", width=200)
                        
                    st.success(f"Registrado en {r} (P{piso}-F{fila}-C{columna}).")
