"""
mqtt_client.py — Conexion MQTT con HiveMQ Cloud.
Usa st.cache_resource para inicializar UNA sola vez por sesion.
"""
import ssl
import streamlit as st
import paho.mqtt.client as mqtt
from config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, TOPIC_SUB, TOPIC_AUTH

def on_message(client, userdata, msg):
    """Callback: procesa mensajes entrantes del broker."""
    payload = msg.payload.decode('utf-8')
    if payload.endswith("_OFF"):
        st.session_state.msg_mqtt_recibido = payload.replace("_OFF", "")
    elif msg.topic == TOPIC_AUTH:
        st.session_state.uid_rfid_recibido = payload.strip().upper()

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
        return client
    except Exception as e:
        st.warning(f"MQTT no disponible: {e}")
        return None

def publicar(rack_id, accion="ON"):
    """Publica un mensaje pick-to-light al ESP32."""
    client = st.session_state.get('mqtt_client')
    if client:
        from config import TOPIC_PUB
        client.publish(TOPIC_PUB, f"{rack_id}_{accion}")
