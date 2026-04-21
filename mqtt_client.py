"""
mqtt_client.py — Conexion MQTT con HiveMQ Cloud.
Usa st.cache_resource para inicializar UNA sola vez por sesion.
Versión mejorada sin warnings de ScriptRunContext.
"""
import ssl
import streamlit as st
import paho.mqtt.client as mqtt
from config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, TOPIC_SUB, TOPIC_AUTH
import threading

# Lock para evitar race conditions
_mqtt_lock = threading.Lock()

def on_message(client, userdata, msg):
    """Callback: procesa mensajes entrantes del broker."""
    try:
        payload = msg.payload.decode('utf-8')
        
        # Usar lock para acceso seguro a session_state
        with _mqtt_lock:
            if payload.endswith("_OFF"):
                # Guardar en una variable temporal que el main loop revisará
                if not hasattr(st, '_mqtt_messages'):
                    st._mqtt_messages = []
                st._mqtt_messages.append(('confirmacion', payload.replace("_OFF", "")))
                
            elif msg.topic == TOPIC_AUTH:
                # Guardar UID RFID
                if not hasattr(st, '_mqtt_messages'):
                    st._mqtt_messages = []
                st._mqtt_messages.append(('rfid', payload.strip().upper()))
    except Exception as e:
        print(f"[MQTT] Error en callback: {e}")

@st.cache_resource(show_spinner=False)
def init_mqtt():
    """
    Inicializa el cliente MQTT UNA sola vez por sesion de Streamlit.
    st.cache_resource garantiza que no se reconecta en cada render.
    """
    try:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        except AttributeError:
            client = mqtt.Client()

        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        client.on_message = on_message
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.subscribe(TOPIC_SUB)
        client.subscribe(TOPIC_AUTH)
        client.loop_start()
        
        print("[MQTT] Cliente inicializado y conectado")
        return client
    except Exception as e:
        print(f"[MQTT] Error al inicializar: {e}")
        return None

def publicar(rack_id, accion="ON"):
    """Publica un mensaje pick-to-light al ESP32."""
    client = st.session_state.get('mqtt_client')
    if client:
        from config import TOPIC_PUB
        try:
            client.publish(TOPIC_PUB, f"{rack_id}_{accion}")
            print(f"[MQTT] Publicado: {rack_id}_{accion}")
        except Exception as e:
            print(f"[MQTT] Error al publicar: {e}")

def procesar_mensajes_mqtt():
    """
    Procesa mensajes MQTT acumulados.
    Llamar esto desde el main loop de Streamlit.
    """
    if not hasattr(st, '_mqtt_messages'):
        return
    
    with _mqtt_lock:
        mensajes = st._mqtt_messages.copy()
        st._mqtt_messages = []
    
    for tipo, payload in mensajes:
        if tipo == 'confirmacion':
            if st.session_state.get('confirmacion_pendiente') == payload:
                st.session_state.confirmacion_pendiente = None
                print(f"[MQTT] Confirmación procesada: {payload}")
                
        elif tipo == 'rfid':
            # IMPORTANTE: Guardar el UID para que login.py lo procese
            st.session_state.uid_rfid_recibido = payload
            print(f"[MQTT] ✓ UID RFID recibido por MQTT: {payload}")
            
            # También guardarlo en archivo local (para compatibilidad)
            try:
                import time
                data = {
                    "uid": payload,
                    "timestamp": time.time()
                }
                with open('rfid_uid.json', 'w') as f:
                    import json
                    json.dump(data, f)
                print(f"[MQTT] ✓ UID también guardado en archivo local")
            except Exception as e:
                print(f"[MQTT] Advertencia: No se pudo guardar en archivo: {e}")
