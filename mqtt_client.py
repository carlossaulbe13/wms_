"""
mqtt_client.py — Conexión MQTT con HiveMQ Cloud mejorada.
Usa queue thread-safe para mensajes RFID.
VERSIÓN 2.0 - CLUSTER NUEVO
"""
import ssl
import streamlit as st
import paho.mqtt.client as mqtt
from config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, TOPIC_SUB, TOPIC_AUTH
import threading
import queue
import time
import warnings

# Suprimir warnings de ScriptRunContext en threads MQTT
warnings.filterwarnings('ignore', message='.*ScriptRunContext.*')

# Queue thread-safe para mensajes RFID
_rfid_queue = queue.Queue()
_mqtt_lock = threading.Lock()

def on_connect(client, userdata, flags, rc):
    """Callback cuando se conecta al broker."""
    if rc == 0:
        print("[MQTT] ✓ Conectado exitosamente")
    else:
        print(f"[MQTT] ✗ Error de conexión. Código: {rc}")

def on_disconnect(client, userdata, rc):
    """Callback cuando se desconecta del broker."""
    print(f"[MQTT] Desconectado. Código: {rc}")
    if rc != 0:
        print("[MQTT] Reconectando...")

def on_message(client, userdata, msg):
    """Callback: procesa mensajes entrantes del broker."""
    try:
        payload = msg.payload.decode('utf-8').strip()
        
        if msg.topic == TOPIC_AUTH:
            # Guardar UID en queue thread-safe (PRIORITARIO)
            uid_upper = payload.upper()
            _rfid_queue.put(('rfid', uid_upper, time.time()))
            print(f"[MQTT] ✓ UID recibido en queue: {uid_upper}")
            
            # Intentar guardar en session_state si existe (opcional)
            try:
                with _mqtt_lock:
                    if hasattr(st, 'session_state'):
                        if 'uid_rfid_buffer' not in st.session_state:
                            st.session_state.uid_rfid_buffer = []
                        st.session_state.uid_rfid_buffer.append({
                            'uid': uid_upper,
                            'timestamp': time.time()
                        })
                        # Mantener solo los últimos 5 UIDs
                        st.session_state.uid_rfid_buffer = st.session_state.uid_rfid_buffer[-5:]
                        print(f"[MQTT] ✓ UID guardado en session_state buffer")
            except Exception as e:
                # No es crítico si falla - el queue es suficiente
                print(f"[MQTT] Advertencia: No se pudo guardar en session_state: {e}")
        
        elif payload.endswith("_OFF"):
            # Confirmación de rack
            rack_id = payload.replace("_OFF", "")
            _rfid_queue.put(('confirmacion', rack_id, time.time()))
            print(f"[MQTT] ✓ Confirmación rack: {rack_id}")
            
    except Exception as e:
        print(f"[MQTT] Error en callback: {e}")

# Cliente MQTT global (singleton manual)
_mqtt_client_instance = None
_mqtt_init_lock = threading.Lock()

def init_mqtt():
    """
    Inicializa el cliente MQTT UNA sola vez (singleton manual).
    Funciona en todas las versiones de Streamlit.
    """
    global _mqtt_client_instance
    
    # Si ya existe, retornarlo
    if _mqtt_client_instance is not None:
        return _mqtt_client_instance
    
    # Lock para evitar múltiples inicializaciones
    with _mqtt_init_lock:
        # Double-check después del lock
        if _mqtt_client_instance is not None:
            return _mqtt_client_instance
        
        try:
            try:
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            except AttributeError:
                client = mqtt.Client()

            # Configurar callbacks
            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message
            
            # Autenticación
            client.username_pw_set(MQTT_USER, MQTT_PASS)
            client.tls_set(cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)
            
            # Conectar con retry
            max_retries = 3
            for intento in range(max_retries):
                try:
                    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                    break
                except Exception as e:
                    print(f"[MQTT] Intento {intento + 1}/{max_retries} falló: {e}")
                    if intento == max_retries - 1:
                        raise
                    time.sleep(2)
            
            # Suscribirse a topics
            client.subscribe(TOPIC_SUB)
            client.subscribe(TOPIC_AUTH)
            
            # Iniciar loop
            client.loop_start()
            
            print("[MQTT] Cliente inicializado correctamente")
            
            # Guardar instancia global
            _mqtt_client_instance = client
            return client
            
        except Exception as e:
            print(f"[MQTT] ✗ Error fatal al inicializar: {e}")
            return None

def obtener_uid_pendiente():
    """
    Obtiene el UID más reciente del queue (no bloqueante).
    Retorna el UID si es menor a 10 segundos, None si no hay.
    """
    uid_mas_reciente = None
    timestamp_mas_reciente = 0
    items_procesados = 0
    
    # Vaciar queue y quedarse con el más reciente
    while not _rfid_queue.empty():
        try:
            tipo, payload, ts = _rfid_queue.get_nowait()
            items_procesados += 1
            if tipo == 'rfid' and ts > timestamp_mas_reciente:
                uid_mas_reciente = payload
                timestamp_mas_reciente = ts
                print(f"[MQTT] Queue procesada: UID={payload}, antigüedad={time.time()-ts:.1f}s")
        except queue.Empty:
            break
    
    if items_procesados > 0:
        print(f"[MQTT] Total items procesados del queue: {items_procesados}")
    
    # Validar antigüedad (10 segundos)
    if uid_mas_reciente:
        edad = time.time() - timestamp_mas_reciente
        if edad < 10:
            print(f"[MQTT] ✓ UID válido retornado: {uid_mas_reciente} (edad: {edad:.1f}s)")
            return uid_mas_reciente
        else:
            print(f"[MQTT] ✗ UID demasiado viejo: {uid_mas_reciente} (edad: {edad:.1f}s)")
    
    return None

def publicar(rack_id, accion="ON"):
    """Publica un mensaje pick-to-light al ESP32."""
    client = st.session_state.get('mqtt_client')
    if client:
        from config import TOPIC_PUB
        try:
            result = client.publish(TOPIC_PUB, f"{rack_id}_{accion}")
            if result.rc == 0:
                print(f"[MQTT] ✓ Publicado: {rack_id}_{accion}")
            else:
                print(f"[MQTT] ✗ Error al publicar (rc={result.rc})")
        except Exception as e:
            print(f"[MQTT] Error al publicar: {e}")

def verificar_conexion():
    """Verifica si el cliente MQTT está conectado."""
    client = st.session_state.get('mqtt_client')
    if client:
        return client.is_connected()
    return False

def procesar_mensajes_mqtt():
    """
    Procesa mensajes MQTT acumulados (para confirmaciones de rack).
    Llamar desde el main loop.
    """
    while not _rfid_queue.empty():
        try:
            tipo, payload, ts = _rfid_queue.get_nowait()
            
            if tipo == 'confirmacion':
                if st.session_state.get('confirmacion_pendiente') == payload:
                    st.session_state.confirmacion_pendiente = None
                    print(f"[MQTT] Confirmación procesada: {payload}")
                    
        except queue.Empty:
            break
