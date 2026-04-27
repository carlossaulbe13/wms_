"""
ui/login.py — Login SIMPLIFICADO sin animaciones
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
import json
import time
import os
import requests

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
    """Lectura cloud desde Firebase con dedup por session_state"""
    try:
        from config import RFID_URL
        res = requests.get(RFID_URL, timeout=5)
        print(f"[LOGIN] Firebase status={res.status_code} body={res.text[:120]}")
        if res.status_code != 200:
            return None
        try:
            data = res.json()
        except Exception as je:
            print(f"[LOGIN] JSON parse error: {je}")
            return None
        if not data or not isinstance(data, dict):
            print("[LOGIN] Firebase vacio o null")
            return None
        uid = data.get('uid', '').strip().upper()
        print(f"[LOGIN] uid='{uid}'")
        if not uid:
            return None

        # Dedup: ignorar si ya procesamos este UID en los ultimos 8s
        last_uid = st.session_state.get('_rfid_last_uid', '')
        last_ts  = st.session_state.get('_rfid_last_ts', 0)
        if uid == last_uid and (time.time() - last_ts) < 8:
            print(f"[LOGIN] UID repetido en session_state — cooldown activo")
            return None

        # Marcar como procesado y borrar nodo Firebase
        st.session_state['_rfid_last_uid'] = uid
        st.session_state['_rfid_last_ts']  = time.time()
        try:
            requests.delete(RFID_URL, timeout=3)
        except Exception:
            pass
        return uid

    except Exception as e:
        print(f"[LOGIN] Error Firebase: {e}")
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Login simplificado"""
    
    print("="*60)
    print("[LOGIN] PANTALLA LOGIN INICIADA")
    print(f"[LOGIN] ES_CLOUD: {ES_CLOUD}")
    print("="*60)
    
    # Refresh cada 2 segundos
    st_autorefresh(interval=2000, key='login_refresh')
    
    # Leer UID según entorno
    print(f"[LOGIN] Intentando leer UID...")
    uid = leer_uid_cloud() if ES_CLOUD else leer_uid_local()
    print(f"[LOGIN] UID obtenido: {uid}")
    
    # Si hay UID, procesar login
    if uid:
        print(f"[LOGIN] UID detectado: {uid}")
        print(f"[LOGIN] Autorizados: {UIDS_AUTORIZADOS}")
        
        if uid in UIDS_AUTORIZADOS:
            print(f"[LOGIN] AUTORIZADO OK")
            st.session_state.autenticado = True
            st.session_state.rol = 'admin'
            st.session_state.session_token = token_secreto + '_admin'
            st.query_params['_s'] = token_secreto + '_admin'
            st.success(f"OK Login RFID exitoso: {uid}")
            time.sleep(1)
            st.rerun()
        else:
            print(f"[LOGIN] NO AUTORIZADO")
            st.error(f"UID no autorizado: {uid}")
    else:
        print(f"[LOGIN] No hay UID pendiente")
    
    # UI simple
    st.title("UMAD WMS")
    st.subheader("Login")
    
    with st.expander("Debug"):
        st.write(f"**Modo:** {'CLOUD' if ES_CLOUD else 'LOCAL'}")
        st.write(f"**Último UID:** {uid or 'Ninguno'}")
        st.write(f"**UIDs autorizados:** {len(UIDS_AUTORIZADOS)} configurados")
    
    st.info(" Pasa tu tarjeta RFID")
    
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
