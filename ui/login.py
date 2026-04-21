"""
ui/login.py — Pantalla de autenticación RFID + contraseña.
VERSIÓN HÍBRIDA - Local (archivo) + Cloud (Firebase)
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
from config import TOKEN_OPERADOR, TOKEN_ADMIN, TOKEN_ADMIN_2
import json
import time
import os

# Archivo donde el bridge serial guarda los UIDs (solo local)
RFID_JSON_PATH = "rfid_uid.json"

# Detectar si estamos en Streamlit Cloud o local
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')

def leer_uid_desde_archivo():
    """Lee el UID desde el archivo JSON generado por serial_rfid_bridge.py (SOLO LOCAL)"""
    print("\n" + "="*60)
    print("[LOGIN] INICIO - Intentando leer archivo RFID (LOCAL)")
    print(f"[LOGIN] Ruta del archivo: {os.path.abspath(RFID_JSON_PATH)}")
    print(f"[LOGIN] Directorio actual: {os.getcwd()}")
    print(f"[LOGIN] ¿Archivo existe? {os.path.exists(RFID_JSON_PATH)}")
    
    try:
        if os.path.exists(RFID_JSON_PATH):
            print(f"[LOGIN] ✓ Archivo encontrado, leyendo contenido...")
            
            with open(RFID_JSON_PATH, 'r') as f:
                data = json.load(f)
            
            print(f"[LOGIN] Contenido del JSON: {data}")
            
            uid = data.get('uid', '').strip().upper()
            ts = data.get('timestamp', 0)
            edad = time.time() - ts
            
            print(f"[LOGIN] UID extraído: '{uid}'")
            print(f"[LOGIN] Timestamp: {ts}")
            print(f"[LOGIN] Antigüedad: {edad:.1f} segundos")
            print(f"[LOGIN] ¿UID válido? {bool(uid)}")
            print(f"[LOGIN] ¿Edad < 10s? {edad < 10}")
            
            if uid and edad < 10:
                # Eliminar archivo para evitar reprocesamiento
                print(f"[LOGIN] ✓✓✓ UID VÁLIDO - Eliminando archivo")
                os.remove(RFID_JSON_PATH)
                print(f"[LOGIN] ✓ Archivo eliminado")
                print(f"[LOGIN] Retornando UID: {uid}")
                print("="*60 + "\n")
                return uid
            else:
                if not uid:
                    print(f"[LOGIN] ✗ UID vacío")
                if edad >= 10:
                    print(f"[LOGIN] ✗ UID expirado ({edad:.1f}s > 10s)")
        else:
            print(f"[LOGIN] ✗ Archivo NO existe en: {os.path.abspath(RFID_JSON_PATH)}")
            
    except json.JSONDecodeError as e:
        print(f"[LOGIN] ✗✗✗ Error JSON: {e}")
    except Exception as e:
        print(f"[LOGIN] ✗✗✗ Error leyendo archivo RFID: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"[LOGIN] Retornando None (no se encontró UID válido)")
    print("="*60 + "\n")
    return None

def leer_uid_desde_firebase():
    """Lee el UID desde Firebase (PARA STREAMLIT CLOUD)"""
    print("\n" + "="*60)
    print("[LOGIN CLOUD] INICIO - Intentando leer UID desde Firebase")
    
    try:
        from firebase import leer_rfid_pendiente
        from config import RFID_URL
        import requests
        
        print(f"[LOGIN CLOUD] URL Firebase: {RFID_URL}")
        
        # Primero hacer request directo para diagnóstico
        try:
            print(f"[LOGIN CLOUD] Haciendo GET a Firebase...")
            res = requests.get(RFID_URL, timeout=5)
            print(f"[LOGIN CLOUD] Status code: {res.status_code}")
            print(f"[LOGIN CLOUD] Response: {res.text[:200]}")  # Primeros 200 chars
            
            if res.status_code == 200:
                data = res.json() if res.json() else None
                print(f"[LOGIN CLOUD] Data parseada: {data}")
                
                if data and isinstance(data, dict):
                    uid_raw = data.get('uid', '')
                    ts_raw = data.get('ts', 0)
                    print(f"[LOGIN CLOUD] UID raw: '{uid_raw}'")
                    print(f"[LOGIN CLOUD] Timestamp raw: {ts_raw}")
                    print(f"[LOGIN CLOUD] Tiempo actual: {time.time()}")
                    
                    if uid_raw and ts_raw:
                        edad = time.time() - ts_raw
                        print(f"[LOGIN CLOUD] Antigüedad: {edad:.1f}s")
                        print(f"[LOGIN CLOUD] ¿Válido? (< 10s): {edad < 10}")
                else:
                    print(f"[LOGIN CLOUD] ✗ Data es null o no es dict")
            else:
                print(f"[LOGIN CLOUD] ✗ Status code no es 200")
                
        except Exception as e:
            print(f"[LOGIN CLOUD] ✗ Error en request directo: {e}")
            import traceback
            traceback.print_exc()
        
        # Ahora usar la función oficial
        print(f"[LOGIN CLOUD] Llamando a leer_rfid_pendiente()...")
        uid = leer_rfid_pendiente()
        
        if uid:
            print(f"[LOGIN CLOUD] ✓✓✓ UID recibido: {uid}")
            print("="*60 + "\n")
            return uid
        else:
            print(f"[LOGIN CLOUD] ✗ No hay UID pendiente")
            
    except ImportError as e:
        print(f"[LOGIN CLOUD] ✗✗✗ Error importando firebase: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"[LOGIN CLOUD] ✗✗✗ Error leyendo Firebase: {e}")
        import traceback
        traceback.print_exc()
    
    print("="*60 + "\n")
    return None

def pantalla_login(token_secreto, token_admin_pwd):
    """Muestra el login con RFID híbrido (local + cloud)."""
    
    # Refresh cada 2 segundos para detectar UID
    st_autorefresh(interval=2000, key='login_rfid_refresh')
    
    # Intentar leer UID según el entorno
    uid_recibido = None
    
    if ES_CLOUD:
        # Streamlit Cloud → Leer desde Firebase
        uid_recibido = leer_uid_desde_firebase()
    else:
        # Local → Leer desde archivo
        uid_recibido = leer_uid_desde_archivo()
    
    # Procesar UID si se detectó
    if uid_recibido:
        print(f"[LOGIN] UID detectado: {uid_recibido}")
        print(f"[LOGIN] UIDs autorizados: {UIDS_AUTORIZADOS}")
        
        if uid_recibido in UIDS_AUTORIZADOS:
            print(f"[LOGIN] ✓✓✓ UID AUTORIZADO - Iniciando sesión")
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
    
    _, col_center, _ = st.columns([1, 2, 1])
    with col_center:
        # Indicador según entorno
        if ES_CLOUD:
            st.info("☁️ **Modo Cloud** - Esperando RFID via Firebase")
        else:
            if os.path.exists(RFID_JSON_PATH):
                st.success("🟢 **Lector RFID Activo** - Archivo detectado")
            else:
                st.info("🔵 **Esperando tarjeta RFID**")
        
        # DIAGNÓSTICO
        with st.expander("🔍 Diagnóstico RFID", expanded=True):  # ← expanded=True para Cloud
            if ES_CLOUD:
                st.code(f"""
Modo: CLOUD (Streamlit Cloud)
Fuente: Firebase HTTP
Último UID detectado: {uid_recibido or 'Ninguno'}
UIDs Autorizados: {UIDS_AUTORIZADOS}
                """)
                
                # Botón de prueba manual
                if st.button("🔬 Probar Lectura Firebase AHORA"):
                    with st.spinner("Leyendo Firebase..."):
                        test_uid = leer_uid_desde_firebase()
                        if test_uid:
                            st.success(f"✓ UID encontrado: {test_uid}")
                        else:
                            st.error("✗ No se encontró UID en Firebase")
                    
                # Mostrar URL
                try:
                    from config import RFID_URL
                    st.caption(f"URL: `{RFID_URL}`")
                except:
                    pass
                    
            else:
                st.code(f"""
Modo: LOCAL
Archivo RFID: {'✓ Existe' if os.path.exists(RFID_JSON_PATH) else '✗ No existe'}
Último UID detectado: {uid_recibido or 'Ninguno'}
UIDs Autorizados: {UIDS_AUTORIZADOS}
                """)
        
        # Tarjeta RFID
        card_class = "card-awake" if uid_recibido else "card-sleeping"
        card_status = "DETECTADO" if uid_recibido else "ESPERANDO"
        card_dots = "•••• •••• •••• ••••" if uid_recibido else ".... .... .... ...."
        
        if ES_CLOUD:
            led_color = "#3b9edd"  # Azul para cloud
            led_text = "Firebase Cloud"
        else:
            led_color = "#22c55e" if os.path.exists(RFID_JSON_PATH) else "#4a5568"
            led_text = "Lector Local"
        
        led_class = "led-active" if uid_recibido else ""
        
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
        if not ES_CLOUD:
            st.caption("Asegúrate de tener `serial_rfid_bridge.py` ejecutándose")
        
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
