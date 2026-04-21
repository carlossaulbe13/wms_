"""
ui/login.py — Login SIMPLIFICADO sin animaciones
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
import json
import time
import os

RFID_JSON_PATH = "rfid_uid.json"
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')

def leer_uid_local():
    """Lectura local desde archivo"""
    try:
        if os.path.exists(RFID_JSON_PATH):
            with open(RFID_JSON_PATH, 'r') as f:
                data = json.load(f)
            uid = data.get('uid', '').strip().upper()
            ts = data.get('timestamp', 0)
            if uid and (time.time() - ts) < 10:
                os.remove(RFID_JSON_PATH)
                return uid
    except:
        pass
    return None

def leer_uid_cloud():
    """Lectura cloud desde Firebase"""
    try:
        from firebase import leer_rfid_pendiente
        uid = leer_rfid_pendiente()
        print(f"[LOGIN] Firebase retornó: {uid}")
        return uid
    except Exception as e:
        print(f"[LOGIN] Error Firebase: {e}")
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Login simplificado"""
    
    # Refresh cada 2 segundos
    st_autorefresh(interval=2000, key='login_refresh')
    
    # Leer UID según entorno
    uid = leer_uid_cloud() if ES_CLOUD else leer_uid_local()
    
    # Si hay UID, procesar login
    if uid:
        print(f"[LOGIN] UID detectado: {uid}")
        print(f"[LOGIN] Autorizados: {UIDS_AUTORIZADOS}")
        
        if uid in UIDS_AUTORIZADOS:
            print(f"[LOGIN] ✓✓✓ AUTORIZADO")
            st.session_state.autenticado = True
            st.session_state.rol = 'admin'
            st.session_state.session_token = token_secreto + '_admin'
            st.query_params['_s'] = token_secreto + '_admin'
            st.success(f"✓ Login RFID exitoso: {uid}")
            time.sleep(1)
            st.rerun()
        else:
            print(f"[LOGIN] ✗ NO AUTORIZADO")
            st.error(f"UID no autorizado: {uid}")
    
    # UI simple
    st.title("UMAD WMS")
    st.subheader("Login")
    
    # Diagnóstico
    with st.expander("🔍 Debug", expanded=True):
        st.write(f"**Modo:** {'CLOUD' if ES_CLOUD else 'LOCAL'}")
        st.write(f"**Último UID:** {uid or 'Ninguno'}")
        st.write(f"**UIDs válidos:** {UIDS_AUTORIZADOS}")
        
        if ES_CLOUD:
            if st.button("🔬 Probar Firebase"):
                test_uid = leer_uid_cloud()
                st.write(f"Resultado: {test_uid}")
    
    st.info("📡 Pasa tu tarjeta RFID")
    
    # Formulario contraseña
    with st.form("login"):
        pwd = st.text_input("Contraseña", type="password")
        submit = st.form_submit_button("Entrar")
        
        if submit:
            if pwd == PASSWORD_ADMIN:
                st.session_state.autenticado = True
                st.session_state.rol = 'admin'
                st.session_state.session_token = token_admin_pwd + '_admin'
                st.query_params['_s'] = token_admin_pwd + '_admin'
                st.rerun()
            elif pwd == PASSWORD_ACCESO:
                st.session_state.autenticado = True
                st.session_state.rol = 'operador'
                st.session_state.session_token = token_secreto + '_operador'
                st.query_params['_s'] = token_secreto + '_operador'
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
