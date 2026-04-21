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

    # Detectar si hay escaneo activo
    hay_escaneo = uid_entrante is not None
    
    # CSS para animaciones
    st.markdown("""
    <style>
    @keyframes wakeUp {
        0% { 
            filter: grayscale(100%) brightness(0.3);
            transform: scale(0.95);
        }
        50% {
            filter: grayscale(50%) brightness(0.6);
            transform: scale(1.05);
        }
        100% { 
            filter: grayscale(0%) brightness(1);
            transform: scale(1);
        }
    }
    
    @keyframes pulse {
        0%, 100% { 
            transform: scale(1);
            box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7);
        }
        50% { 
            transform: scale(1.05);
            box-shadow: 0 0 0 10px rgba(34, 197, 94, 0);
        }
    }
    
    @keyframes slideDown {
        0% { 
            transform: translateY(-30px);
            opacity: 0;
        }
        100% { 
            transform: translateY(0);
            opacity: 1;
        }
    }
    
    .card-sleeping {
        filter: grayscale(100%) brightness(0.3);
        opacity: 0.5;
        transition: all 0.3s ease;
    }
    
    .card-awake {
        animation: wakeUp 1s ease-out forwards;
    }
    
    .success-text {
        animation: slideDown 0.8s ease-out;
    }
    
    .led-active {
        animation: pulse 1.5s ease-in-out infinite;
    }
    </style>
    """, unsafe_allow_html=True)

    # Título
    st.markdown("<h1 style='text-align:center;color:#FF4B4B;font-size:42px;margin:40px 0 8px 0;letter-spacing:2px;'>UMAD WMS</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#8892b0;font-size:15px;margin-bottom:40px;'>Warehouse Management System</p>", unsafe_allow_html=True)

    # Contenedor de la tarjeta RFID
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        # Determinar clase CSS según estado
        card_class = "card-awake" if hay_escaneo else "card-sleeping"
        
        st.markdown(f"""
        <div style='background:#1a1f35;border:2px solid #3a3f55;border-radius:20px;
                    padding:40px;text-align:center;margin-bottom:30px;' class='{card_class}'>
            
            <div style='font-size:80px;margin-bottom:20px;'>💳</div>
            
            <div style='background:#2d3548;border-radius:10px;padding:20px;margin-bottom:20px;'>
                <div style='color:#8892b0;font-size:12px;text-transform:uppercase;margin-bottom:8px;'>
                    {'✅ TARJETA DETECTADA' if hay_escaneo else '⏸️ ESPERANDO TARJETA'}
                </div>
                <div style='color:#cdd3ea;font-family:monospace;font-size:20px;letter-spacing:4px;'>
                    {'•••• •••• •••• ••••' if hay_escaneo else '.... .... .... ....'}
                </div>
            </div>
            
            <div style='display:flex;justify-content:center;align-items:center;gap:10px;'>
                <div style='width:12px;height:12px;background:{'#22c55e' if hay_escaneo else '#4a5568'};
                            border-radius:50%;' class='{'led-active' if hay_escaneo else ''}'></div>
                <span style='color:#8892b0;font-size:14px;'>
                    {'Lector Activo' if hay_escaneo else 'Lector en Espera'}
                </span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Mostrar mensaje de éxito o error
        if hay_escaneo:
            if uid_entrante in UIDS_AUTORIZADOS:
                st.markdown("<div class='success-text'>", unsafe_allow_html=True)
                st.success("🎉 **¡Acceso Autorizado!**\n\nIniciando sesión...")
                st.markdown("</div>", unsafe_allow_html=True)
                time.sleep(1.5)
                st.rerun()
            else:
                st.error(f"⚠️ **Acceso Denegado**\n\nUID no autorizado: `{uid_entrante}`")
        else:
            st.info("📡 **Acerca tu tarjeta RFID al lector**\n\nEl lector está conectado al ESP32")
        
        st.divider()
        st.caption("— o ingresa tu contraseña —")
        
        # Formulario de contraseña
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

def _conceder_acceso(rol, token):
    st.session_state.autenticado       = True
    st.session_state.rol               = rol
    st.session_state.intentos_password = 0
    st.session_state.session_token     = token
    st.query_params['_s'] = token
    st.rerun()
