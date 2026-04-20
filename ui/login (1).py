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

def leer_rfid_local():
    """Lee el UID desde archivo local generado por serial_rfid_bridge.py"""
    try:
        if os.path.exists('rfid_uid.json'):
            with open('rfid_uid.json', 'r') as f:
                data = json.load(f)
            
            uid = data.get('uid', '').strip().upper()
            ts = data.get('timestamp', 0)
            
            # Verificar que no sea muy viejo (máximo 10 segundos)
            if uid and (time.time() - ts) < 10:
                # Limpiar el archivo para no reprocesar
                os.remove('rfid_uid.json')
                return uid
    except Exception as e:
        pass
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Muestra el login. Llama st.rerun() si el acceso es concedido."""

    # Autorefresh para detectar tarjeta RFID cada 2 segundos
    st_autorefresh(interval=2000, key='login_rfid_refresh')

    # Leer UID desde archivo local (en lugar de Firebase)
    uid_local = leer_rfid_local()
    if uid_local:
        st.session_state.uid_rfid_recibido = uid_local

    uid_entrante = st.session_state.get('uid_rfid_recibido')
    if uid_entrante:
        st.session_state.uid_rfid_recibido = None
        if uid_entrante in UIDS_AUTORIZADOS:
            _conceder_acceso('admin', token_secreto + '_admin')
            return
        else:
            st.session_state.intentos_password += 1

    # Bloqueo
    import time
    bloqueado_hasta = st.session_state.get('bloqueado_hasta', 0.0)
    restante = bloqueado_hasta - time.time()
    if restante > 0:
        st.markdown(f"""
        <div style='max-width:420px;margin:10vh auto;background:#1e1e2e;
             border:1.5px solid #dc3545;border-radius:14px;padding:40px 36px;text-align:center;'>
          <h2 style='color:#ef4444;margin-bottom:8px;'>Acceso bloqueado</h2>
          <p style='color:#8892b0;font-size:13px;'>Intenta de nuevo en
          <b style='color:#cdd3ea;'>{restante:.0f} segundos</b>.</p>
        </div>""", unsafe_allow_html=True)
        st_autorefresh(interval=1000, key='bloqueo_refresh')
        return

    # UI con fuente más grande
    st.markdown("""
    <div style='max-width:420px;margin:8vh auto 0;text-align:center;'>
      <h1 style='color:#FF4B4B;font-size:36px;margin-bottom:8px;'>UMAD WMS</h1>
      <p style='color:#8892b0;font-size:15px;margin-bottom:32px;'>Warehouse Management System</p>
    </div>""", unsafe_allow_html=True)

    _, col_c, _ = st.columns([1, 2, 1])
    with col_c:
        rfid_denegado = uid_entrante and uid_entrante not in UIDS_AUTORIZADOS
        st.markdown("""
        <div style='background:#16192a;border:1.5px solid #3a3f55;border-radius:12px;
             padding:24px;text-align:center;margin-bottom:16px;'>
          <p style='color:#cdd3ea;font-size:14px;font-weight:600;margin-bottom:4px;'>
            Acerca tu tarjeta RFID al lector</p>
          <p style='color:#8892b0;font-size:11px;'>El lector esta conectado al ESP32</p>
        </div>""", unsafe_allow_html=True)

        if rfid_denegado:
            st.error(f"UID no autorizado: {uid_entrante}")

        st.markdown("<p style='text-align:center;color:#8892b0;font-size:12px;margin:8px 0;'>"
                    "— o ingresa tu contrasena —</p>", unsafe_allow_html=True)

        with st.form("login_form"):
            pwd = st.text_input("Contrasena", type="password",
                                placeholder="Ingresa la contrasena de acceso")
            if st.form_submit_button("Entrar", use_container_width=True):
                if pwd == PASSWORD_ADMIN:
                    _conceder_acceso('admin', token_admin_pwd + '_admin')
                elif pwd == PASSWORD_ACCESO:
                    _conceder_acceso('operador', token_secreto + '_operador')
                else:
                    st.session_state.intentos_password += 1
                    intentos = st.session_state.intentos_password
                    if intentos >= 3:
                        import time as _t
                        st.session_state.bloqueado_hasta = _t.time() + 30
                        st.rerun()
                    else:
                        st.error(f"Contrasena incorrecta. Intento {intentos}/3.")

def _conceder_acceso(rol, token):
    st.session_state.autenticado       = True
    st.session_state.rol               = rol
    st.session_state.intentos_password = 0
    st.session_state.session_token     = token
    st.query_params['_s'] = token
    st.rerun()
