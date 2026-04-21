"""
ui/login.py — Pantalla de autenticacion RFID + contrasena.
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
from config import TOKEN_OPERADOR, TOKEN_ADMIN, TOKEN_ADMIN_2
import json
import time
import os

# Detectar si estamos en Streamlit Cloud o local
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')

if not ES_CLOUD:
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RFID_JSON_PATH = os.path.join(SCRIPT_DIR, 'rfid_uid.json')
else:
    from firebase import leer_rfid_pendiente

def leer_rfid_local():
    """Lee el UID desde archivo local generado por serial_rfid_bridge.py"""
    try:
        if os.path.exists(RFID_JSON_PATH):
            print(f"[DEBUG] rfid_uid.json encontrado en: {RFID_JSON_PATH}")
            with open(RFID_JSON_PATH, 'r') as f:
                data = json.load(f)
            
            uid = data.get('uid', '').strip().upper()
            ts = data.get('timestamp', 0)
            edad = time.time() - ts
            
            print(f"[DEBUG] UID leído: {uid}")
            print(f"[DEBUG] Edad del UID: {edad:.1f} segundos")
            
            if uid and edad < 10:
                print(f"[DEBUG] UID válido, eliminando archivo")
                os.remove(RFID_JSON_PATH)
                return uid
            else:
                print(f"[DEBUG] UID muy viejo o vacío, ignorando")
    except Exception as e:
        print(f"[DEBUG] Error leyendo RFID: {e}")
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Muestra el login. Llama st.rerun() si el acceso es concedido."""

    st_autorefresh(interval=2000, key='login_rfid_refresh')

    uid_recibido = None
    
    if 'uid_rfid_recibido' in st.session_state and st.session_state.uid_rfid_recibido:
        uid_recibido = st.session_state.uid_rfid_recibido
        print(f"[DEBUG] UID recibido desde MQTT: {uid_recibido}")
    elif not ES_CLOUD:
        uid_recibido = leer_rfid_local()
        if uid_recibido:
            print(f"[DEBUG] UID recibido desde archivo local: {uid_recibido}")
    else:
        uid_recibido = leer_rfid_pendiente()
        if uid_recibido:
            print(f"[DEBUG] UID recibido desde Firebase: {uid_recibido}")
    
    if uid_recibido:
        st.session_state.uid_rfid_recibido = uid_recibido

    uid_entrante = st.session_state.get('uid_rfid_recibido')
    if uid_entrante:
        print(f"[DEBUG] UID entrante detectado: {uid_entrante}")
        st.session_state.uid_rfid_recibido = None
        
        print(f"[DEBUG] UIDs autorizados: {UIDS_AUTORIZADOS}")
        
        if uid_entrante in UIDS_AUTORIZADOS:
            print(f"[DEBUG] UID AUTORIZADO - Iniciando sesión")
            _conceder_acceso('admin', token_secreto + '_admin')
            return
        else:
            print(f"[DEBUG] UID NO AUTORIZADO")
            st.session_state.intentos_password += 1

    # Bloqueo
    bloqueado_hasta = st.session_state.get('bloqueado_hasta', 0.0)
    restante = bloqueado_hasta - time.time()
    if restante > 0:
        st.error(f"🔒 **Acceso bloqueado**\n\nIntenta de nuevo en **{restante:.0f} segundos**")
        st_autorefresh(interval=1000, key='bloqueo_refresh')
        return

    # UI Simple con Streamlit nativo
    st.markdown("# UMAD WMS")
    st.caption("Warehouse Management System")
    st.divider()
    
    # Mensaje RFID
    _, col, _ = st.columns([1, 3, 1])
    with col:
        if uid_entrante and uid_entrante not in UIDS_AUTORIZADOS:
            st.error(f"⚠️ **Acceso Denegado**\n\nUID no autorizado: `{uid_entrante}`")
        
        st.info("📡 **Acerca tu tarjeta RFID al lector**\n\nEl lector está conectado al ESP32")
        
        st.divider()
        st.caption("— o ingresa tu contraseña —")
        
        with st.form("login_form"):
            pwd = st.text_input("Contraseña", type="password", 
                              placeholder="Ingresa la contraseña de acceso")
            if st.form_submit_button("🔐 Iniciar Sesión", use_container_width=True, type="primary"):
                if pwd == PASSWORD_ADMIN:
                    _conceder_acceso('admin', token_admin_pwd + '_admin')
                elif pwd == PASSWORD_ACCESO:
                    _conceder_acceso('operador', token_secreto + '_operador')
                else:
                    st.session_state.intentos_password += 1
                    intentos = st.session_state.intentos_password
                    if intentos >= 3:
                        st.session_state.bloqueado_hasta = time.time() + 30
                        st.rerun()
                    else:
                        st.error(f"Contraseña incorrecta. Intento {intentos}/3.")

def _conceder_acceso(rol, token):
    st.session_state.autenticado       = True
    st.session_state.rol               = rol
    st.session_state.intentos_password = 0
    st.session_state.session_token     = token
    st.query_params['_s'] = token
    st.rerun()
