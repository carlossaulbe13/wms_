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
    """Lectura cloud desde Firebase"""
    print("\n" + "="*50)
    print("[LOGIN CLOUD] Iniciando lectura Firebase...")
    
    try:
        # Importar y obtener URL
        from firebase import leer_rfid_pendiente
        from config import RFID_URL
        import requests
        
        print(f"[LOGIN CLOUD] URL: {RFID_URL}")
        
        # Request directo para debug
        try:
            res = requests.get(RFID_URL, timeout=5)
            print(f"[LOGIN CLOUD] Status: {res.status_code}")
            print(f"[LOGIN CLOUD] Raw response: {res.text}")
            
            if res.status_code == 200:
                data = res.json() if res.text and res.text != 'null' else None
                print(f"[LOGIN CLOUD] Parsed data: {data}")
                
                if data:
                    uid_raw = data.get('uid', '')
                    ts_raw = data.get('ts', 0)
                    print(f"[LOGIN CLOUD] UID raw: '{uid_raw}' (type: {type(uid_raw)})")
                    print(f"[LOGIN CLOUD] TS raw: {ts_raw}")
                    
                    if uid_raw:
                        edad = time.time() - ts_raw
                        print(f"[LOGIN CLOUD] Edad: {edad:.1f}s")
                        print(f"[LOGIN CLOUD] Valido?: {edad < 10}")
                        
        except Exception as e:
            print(f"[LOGIN CLOUD] Error request directo: {e}")
        
        # Usar función oficial
        print(f"[LOGIN CLOUD] Llamando leer_rfid_pendiente()...")
        uid = leer_rfid_pendiente()
        print(f"[LOGIN CLOUD] Resultado: '{uid}' (type: {type(uid)})")
        print("="*50 + "\n")
        
        return uid
        
    except Exception as e:
        print(f"[LOGIN CLOUD] ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("="*50 + "\n")
    
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
    
    # Diagnóstico SIEMPRE VISIBLE en Cloud
    if ES_CLOUD:
        st.warning("MODO CLOUD - Leyendo desde Firebase")
        st.write(f"**Último UID:** {uid or 'Ninguno'}")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button(" PROBAR FIREBASE AHORA", type="primary"):
                with st.spinner("Leyendo Firebase..."):
                    test_uid = leer_uid_cloud()
                    if test_uid:
                        st.success(f"✓ UID: {test_uid}")
                    else:
                        st.error("✗ Firebase vacío o UID expirado")
        with col2:
            # Mostrar URL de Firebase
            try:
                from config import RFID_URL
                st.caption(f"`{RFID_URL}`")
            except:
                pass
    
    # Diagnóstico local
    with st.expander(" Debug Completo"):
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
