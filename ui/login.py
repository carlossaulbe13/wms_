"""
ui/login.py — Pantalla de autenticación RFID + contraseña MEJORADA.
VERSIÓN 2.0 - MQTT optimizado con queue thread-safe
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
from config import TOKEN_OPERADOR, TOKEN_ADMIN, TOKEN_ADMIN_2
import json
import time
import os

# Detectar entorno
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')

if not ES_CLOUD:
    SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RFID_JSON_PATH = os.path.join(SCRIPT_DIR, 'rfid_uid.json')
else:
    from firebase import leer_rfid_pendiente

def leer_rfid_local():
    """Lee el UID desde archivo local (desarrollo)."""
    try:
        if os.path.exists(RFID_JSON_PATH):
            with open(RFID_JSON_PATH, 'r') as f:
                data = json.load(f)
            
            uid = data.get('uid', '').strip().upper()
            ts = data.get('timestamp', 0)
            edad = time.time() - ts
            
            if uid and edad < 10:
                os.remove(RFID_JSON_PATH)
                return uid
    except Exception as e:
        print(f"[DEBUG] Error leyendo RFID local: {e}")
    return None

def obtener_uid_desde_mqtt():
    """
    Obtiene UID desde MQTT usando la función mejorada.
    Prioriza queue sobre session_state.
    """
    from mqtt_client import obtener_uid_pendiente
    
    # 1. Intentar desde queue (más confiable)
    uid_queue = obtener_uid_pendiente()
    if uid_queue:
        print(f"[LOGIN] UID desde MQTT queue: {uid_queue}")
        return uid_queue
    
    # 2. Fallback: revisar buffer en session_state
    if 'uid_rfid_buffer' in st.session_state:
        buffer = st.session_state.uid_rfid_buffer
        if buffer:
            # Tomar el más reciente que tenga menos de 10 segundos
            for item in reversed(buffer):
                edad = time.time() - item['timestamp']
                if edad < 10:
                    uid = item['uid']
                    # Marcar como procesado
                    st.session_state.uid_rfid_buffer.remove(item)
                    print(f"[LOGIN] UID desde buffer: {uid}")
                    return uid
    
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Muestra el login con RFID mejorado."""
    
    # CRÍTICO: Procesar mensajes MQTT antes de verificar UID
    from mqtt_client import procesar_mensajes_mqtt
    procesar_mensajes_mqtt()
    
    # Refresh más agresivo para MQTT (1 segundo)
    st_autorefresh(interval=1000, key='login_rfid_refresh')
    
    # Estado de conexión MQTT
    from mqtt_client import verificar_conexion
    mqtt_conectado = verificar_conexion()
    
    uid_recibido = None
    
    # Obtener UID desde diferentes fuentes (prioridad)
    if mqtt_conectado:
        uid_recibido = obtener_uid_desde_mqtt()
    
    if not uid_recibido and not ES_CLOUD:
        uid_recibido = leer_rfid_local()
    
    if not uid_recibido and ES_CLOUD:
        uid_recibido = leer_rfid_pendiente()
    
    # Procesar UID si se detectó
    if uid_recibido:
        print(f"[LOGIN] UID detectado: {uid_recibido}")
        print(f"[LOGIN] UIDs autorizados: {UIDS_AUTORIZADOS}")
        
        if uid_recibido in UIDS_AUTORIZADOS:
            print(f"[LOGIN] ✓ UID AUTORIZADO")
            _conceder_acceso('admin', token_secreto + '_admin')
            return
        else:
            print(f"[LOGIN] ✗ UID NO AUTORIZADO")
            st.session_state.intentos_password = st.session_state.get('intentos_password', 0) + 1
            st.error(f"⚠️ **Acceso Denegado** - UID: `{uid_recibido}`")
            time.sleep(2)
    
    # Bloqueo por intentos fallidos
    bloqueado_hasta = st.session_state.get('bloqueado_hasta', 0.0)
    restante = bloqueado_hasta - time.time()
    if restante > 0:
        st.error(f"🔒 **Acceso bloqueado**\n\nIntenta en **{restante:.0f}s**")
        st_autorefresh(interval=1000, key='bloqueo_refresh')
        return
    
    # UI
    st.markdown("<h1 style='text-align:center;color:#FF4B4B;font-size:42px;margin:40px 0 8px 0;'>UMAD WMS</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center;color:#8892b0;font-size:15px;margin-bottom:40px;'>Warehouse Management System</p>", unsafe_allow_html=True)
    
    # Indicador de conexión MQTT
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        if mqtt_conectado:
            st.success("🟢 **MQTT Conectado** - Lector activo")
        else:
            st.warning("🟡 **MQTT Desconectado** - Verifica conexión")
        
        # Tarjeta RFID
        card_class = "card-awake" if uid_recibido else "card-sleeping"
        card_status = "AUTORIZADO" if uid_recibido else "ESPERANDO"
        card_dots = "•••• •••• •••• ••••" if uid_recibido else ".... .... .... ...."
        led_color = "#22c55e" if mqtt_conectado else "#dc3545"
        led_class = "led-active" if mqtt_conectado else ""
        led_text = "Lector Activo" if mqtt_conectado else "Lector Inactivo"
        
        st.html(f"""
        <style>
        @keyframes wakeUp {{
            0% {{ filter: grayscale(100%) brightness(0.3); transform: scale(0.95); }}
            50% {{ filter: grayscale(50%) brightness(0.6); transform: scale(1.05); }}
            100% {{ filter: grayscale(0%) brightness(1); transform: scale(1); }}
        }}
        
        @keyframes pulse {{
            0%, 100% {{ transform: scale(1); box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
            50% {{ transform: scale(1.05); box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }}
        }}
        
        .card-sleeping {{
            filter: grayscale(100%) brightness(0.3);
            opacity: 0.5;
        }}
        
        .card-awake {{
            animation: wakeUp 1s ease-out forwards;
        }}
        
        .led-active {{
            animation: pulse 1.5s ease-in-out infinite;
        }}
        </style>
        
        <div style='background:#1a1f35;border:2px solid #3a3f55;border-radius:20px;
                    padding:40px;text-align:center;margin-bottom:20px;' class='{card_class}'>
            
            <div style='width:280px;height:180px;margin:0 auto 20px;
                        background:linear-gradient(135deg,#2d3548,#1a1f35);
                        border:2px solid #4a5080;border-radius:15px;padding:20px;
                        box-shadow:0 10px 30px rgba(0,0,0,0.5);'>
                
                <div style='width:50px;height:40px;
                            background:linear-gradient(135deg,#ffd700,#ffed4e);
                            border-radius:6px;margin-bottom:30px;'></div>
                
                <div style='color:#cdd3ea;font-family:monospace;font-size:18px;
                            letter-spacing:3px;margin:20px 0;'>{card_dots}</div>
                
                <div style='display:flex;justify-content:space-between;margin-top:30px;'>
                    <div style='text-align:left;'>
                        <div style='color:#8892b0;font-size:10px;text-transform:uppercase;'>
                            {card_status}</div>
                        <div style='color:#cdd3ea;font-size:14px;font-weight:600;'>
                            RFID CARD</div>
                    </div>
                    <div style='text-align:right;'>
                        <div style='color:#8892b0;font-size:10px;text-transform:uppercase;'>
                            SISTEMA</div>
                        <div style='color:#cdd3ea;font-size:14px;font-weight:600;'>
                            WMS</div>
                    </div>
                </div>
            </div>
            
            <div style='display:flex;justify-content:center;align-items:center;gap:10px;'>
                <div style='width:12px;height:12px;background:{led_color};
                            border-radius:50%;' class='{led_class}'></div>
                <span style='color:#8892b0;font-size:14px;'>{led_text}</span>
            </div>
        </div>
        """)
        
        st.info("📡 **Acerca tu tarjeta RFID al lector**")
        
        st.divider()
        st.caption("— o ingresa tu contraseña —")
        
        # Formulario de contraseña
        with st.form("login_form"):
            pwd = st.text_input(
                "Contraseña", 
                type="password", 
                placeholder="Ingresa la contraseña de acceso",
                label_visibility="collapsed"
            )
            
            if st.form_submit_button("🔐 Iniciar Sesión", use_container_width=True, type="primary"):
                if pwd == PASSWORD_ADMIN:
                    _conceder_acceso('admin', token_admin_pwd + '_admin')
                elif pwd == PASSWORD_ACCESO:
                    _conceder_acceso('operador', token_secreto + '_operador')
                else:
                    intentos = st.session_state.get('intentos_password', 0) + 1
                    st.session_state.intentos_password = intentos
                    if intentos >= 3:
                        st.session_state.bloqueado_hasta = time.time() + 30
                        st.rerun()
                    else:
                        st.error(f"❌ Contraseña incorrecta. Intento {intentos}/3.")

def _conceder_acceso(rol, token):
    """Concede acceso y redirige."""
    st.session_state.autenticado = True
    st.session_state.rol = rol
    st.session_state.intentos_password = 0
    st.session_state.session_token = token
    st.query_params['_s'] = token
    st.success(f"✅ Acceso concedido como {rol}")
    time.sleep(0.5)
    st.rerun()
