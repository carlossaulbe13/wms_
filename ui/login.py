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
    # Modo LOCAL: usa archivo JSON del bridge serial
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RFID_JSON_PATH = os.path.join(SCRIPT_DIR, 'rfid_uid.json')
else:
    # Modo CLOUD: usa Firebase
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
            
            # Verificar que no sea muy viejo (máximo 10 segundos)
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

    # Autorefresh para detectar tarjeta RFID cada 2 segundos
    st_autorefresh(interval=2000, key='login_rfid_refresh')

    # Prioridad de lectura:
    # 1. MQTT (si hay cliente MQTT conectado)
    # 2. Archivo local (si existe)
    # 3. Firebase (si estamos en cloud)
    
    uid_recibido = None
    
    # Primero: intentar leer desde session_state (MQTT ya lo puso ahí)
    if 'uid_rfid_recibido' in st.session_state and st.session_state.uid_rfid_recibido:
        uid_recibido = st.session_state.uid_rfid_recibido
        print(f"[DEBUG] UID recibido desde MQTT: {uid_recibido}")
    
    # Segundo: intentar leer desde archivo local
    elif not ES_CLOUD:
        uid_recibido = leer_rfid_local()
        if uid_recibido:
            print(f"[DEBUG] UID recibido desde archivo local: {uid_recibido}")
    
    # Tercero: leer desde Firebase (solo en cloud)
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
        st.markdown(f"""
        <div style='max-width:420px;margin:10vh auto;background:#16192a;
             border:1.5px solid #ef4444;border-radius:12px;padding:32px;text-align:center;'>
          <h2 style='color:#ef4444;margin-bottom:8px;'>Acceso bloqueado</h2>
          <p style='color:#8892b0;font-size:13px;'>Intenta de nuevo en
          <b style='color:#cdd3ea;'>{restante:.0f} segundos</b>.</p>
        </div>""", unsafe_allow_html=True)
        st_autorefresh(interval=1000, key='bloqueo_refresh')
        return

    # Título
    st.markdown("<h1 style='text-align:center;color:#FF4B4B;font-size:42px;margin:40px 0 8px 0;letter-spacing:2px;'>UMAD WMS</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#8892b0;font-size:15px;margin-bottom:40px;'>Warehouse Management System</p>", unsafe_allow_html=True)

    # Crear el lector RFID con HTML más simple
    st.markdown("""
    <style>
    @keyframes scan{0%,100%{opacity:0}50%{opacity:1}}
    @keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
    @keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}
    @keyframes wave{0%{transform:scale(1);opacity:.7}100%{transform:scale(1.5);opacity:0}}
    
    .rfid-box{max-width:500px;margin:0 auto 30px;background:#1a1f35;border:2px solid #3a3f55;
    border-radius:20px;padding:50px 40px;box-shadow:0 10px 40px rgba(0,0,0,.5);position:relative}
    
    .card{width:280px;height:180px;margin:0 auto 30px;background:linear-gradient(135deg,#2d3548,#1a1f35);
    border:2px solid #4a5080;border-radius:15px;padding:20px;box-shadow:0 10px 30px rgba(0,0,0,.5);
    animation:float 2s ease-in-out infinite}
    
    .chip{width:50px;height:40px;background:linear-gradient(135deg,#ffd700,#ffed4e);
    border-radius:6px;margin-bottom:15px}
    
    .reader{width:120px;height:120px;margin:20px auto;background:#2a2f45;
    border:3px solid #4a5080;border-radius:15px;display:flex;align-items:center;
    justify-content:center;position:relative;box-shadow:0 5px 20px rgba(255,75,75,.3)}
    
    .wave{position:absolute;width:100%;height:100%;border:2px solid #FF4B4B;
    border-radius:15px;animation:wave 2s ease-out infinite}
    .wave:nth-child(2){animation-delay:.5s}
    .wave:nth-child(3){animation-delay:1s}
    
    .led{display:inline-block;width:12px;height:12px;background:#22c55e;
    border-radius:50%;box-shadow:0 0 10px #22c55e;animation:pulse 1.5s ease-in-out infinite}
    </style>
    
    <div class="rfid-box">
        <div class="card">
            <div class="chip"></div>
            <div style="color:#cdd3ea;font-family:monospace;font-size:18px;letter-spacing:3px;margin:15px 0">
                •••• •••• •••• ••••
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:20px">
                <div>
                    <div style="color:#8892b0;font-size:10px;text-transform:uppercase">Autorizado</div>
                    <div style="color:#cdd3ea;font-size:14px;font-weight:600">RFID CARD</div>
                </div>
                <div style="text-align:right">
                    <div style="color:#8892b0;font-size:10px;text-transform:uppercase">Sistema</div>
                    <div style="color:#cdd3ea;font-size:14px;font-weight:600">WMS</div>
                </div>
            </div>
        </div>
        
        <svg width="100" height="40" style="margin:20px auto;display:block">
            <path d="M10,20 L45,5 L45,35 L10,20" fill="#8892b0" opacity=".5"/>
            <path d="M90,20 L55,5 L55,35 L90,20" fill="#8892b0" opacity=".5"/>
        </svg>
        
        <div class="reader">
            <div class="wave"></div>
            <div class="wave"></div>
            <div class="wave"></div>
            <span style="font-size:48px;z-index:1">📡</span>
        </div>
        
        <p style="color:#cdd3ea;font-size:16px;font-weight:600;text-align:center;margin:20px 0 8px">
            <span class="led"></span> Acerca tu tarjeta RFID al lector
        </p>
        <p style="color:#8892b0;font-size:12px;text-align:center">El lector está conectado al ESP32</p>
    </div>
    """, unsafe_allow_html=True)

    # Mostrar error si UID no autorizado
    uid_actual = st.session_state.get('uid_rfid_recibido')
    if uid_entrante and uid_entrante not in UIDS_AUTORIZADOS:
        st.markdown(f"""
        <div style='max-width:500px;margin:20px auto;background:#7f1d1d;border:2px solid #ef4444;
        border-radius:12px;padding:20px;text-align:center'>
            <p style='color:#fca5a5;font-size:16px;font-weight:600;margin:0 0 8px 0'>⚠️ Acceso Denegado</p>
            <p style='color:#fca5a5;font-size:13px;margin:0'>UID no autorizado: {uid_entrante}</p>
        </div>
        """, unsafe_allow_html=True)

    # Formulario de contraseña
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("""
        <div style='text-align:center;color:#8892b0;font-size:13px;margin:30px 0 20px;position:relative'>
            <span style='background:#0e1117;padding:0 15px;position:relative;z-index:1'>
                o ingresa tu contraseña
            </span>
            <div style='position:absolute;top:50%;left:0;right:0;height:1px;
            background:linear-gradient(90deg,transparent,#3a3f55,transparent);z-index:0'></div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<div style='background:#16192a;border:1.5px solid #3a3f55;border-radius:12px;padding:24px'>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            pwd = st.text_input("Contraseña", type="password",
                                placeholder="Ingresa la contraseña de acceso",
                                label_visibility="collapsed")
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
        
        st.markdown("</div>", unsafe_allow_html=True)

def _conceder_acceso(rol, token):
    st.session_state.autenticado       = True
    st.session_state.rol               = rol
    st.session_state.intentos_password = 0
    st.session_state.session_token     = token
    st.query_params['_s'] = token
    st.rerun()
