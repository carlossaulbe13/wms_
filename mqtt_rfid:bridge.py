"""
mqtt_rfid_bridge.py — Suscriptor MQTT para lecturas RFID.

Corre en paralelo a Streamlit (proceso separado).
Escucha el tópico wms/rfid y vuelca cada UID a rfid_uid.json,
que leer_uid_local() en login.py consume.

Arranque:
    python mqtt_rfid_bridge.py

El ESP debe publicar al tópico configurado en MQTT_TOPIC_RFID (default: wms/rfid).
Formatos aceptados del payload:
    - string plano:  A1:B2:C3:D4
    - JSON:          {"uid": "A1:B2:C3:D4"}
"""

import json
import ssl
import sys
import time
import logging
import os

sys.path.insert(0, os.path.dirname(__file__))

import paho.mqtt.client as mqtt
from config import MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS, MQTT_TOPIC_RFID

RFID_JSON_PATH = "rfid_uid.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MQTT-RFID] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def _parse_uid(payload_bytes: bytes) -> str | None:
    """Extrae el UID del payload; acepta string plano o JSON {"uid": ...}."""
    try:
        text = payload_bytes.decode("utf-8").strip()
    except Exception:
        return None

    # Intenta JSON
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            uid = data.get("uid") or data.get("UID") or data.get("id")
            return str(uid).strip().upper() if uid else None
    except Exception:
        pass

    # String plano
    return text.upper() if text else None


def _on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("Conectado a HiveMQ — suscribiendo a '%s'", MQTT_TOPIC_RFID)
        client.subscribe(MQTT_TOPIC_RFID, qos=1)
    else:
        log.error("Fallo de conexión, código rc=%d", rc)


def _on_disconnect(client, userdata, rc, properties=None, reasoncode=None):
    log.warning("Desconectado (rc=%d) — reconectando en 5 s…", rc)


def _on_message(client, userdata, msg):
    uid = _parse_uid(msg.payload)
    if not uid:
        log.warning("Payload vacío o no parseable: %r", msg.payload)
        return

    entry = {"uid": uid, "timestamp": time.time()}
    try:
        with open(RFID_JSON_PATH, "w") as f:
            json.dump(entry, f)
        log.info("UID recibido y escrito: %s", uid)
    except Exception as e:
        log.error("Error escribiendo %s: %s", RFID_JSON_PATH, e)


def main():
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="wms-rfid-bridge",
        clean_session=True,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(False)

    client.on_connect    = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message    = _on_message

    log.info("Conectando a %s:%d …", MQTT_HOST, MQTT_PORT)

    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_forever(retry_first_connection=True)
        except Exception as e:
            log.error("Error de conexión: %s — reintentando en 10 s", e)
            time.sleep(10)


if __name__ == "__main__":
    main()
