"""
config.py — Credenciales, constantes y helpers de configuracion.
Lee de st.secrets (Streamlit Cloud) o de .env (local).
"""
import os
import streamlit as st

# ── Cargar .env en desarrollo local ──────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def get_secret(key, default=""):
    """Lee de st.secrets primero, luego env, luego default."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

# ── Firebase ─────────────────────────────────────────────────
FIREBASE_URL  = get_secret("FIREBASE_URL",
    "https://umad-wms-default-rtdb.firebaseio.com/")
HISTORIAL_URL = FIREBASE_URL.replace("maestro_articulos.json", "historial.json")
RFID_URL      = FIREBASE_URL.replace("maestro_articulos.json", "rfid_pendiente.json")

# ── MQTT ─────────────────────────────────────────────────────
MQTT_HOST  = get_secret("MQTT_HOST",  "c59a1236477049b7b1b18936e8a242ea.s1.eu.hivemq.cloud")
MQTT_PORT  = int(get_secret("MQTT_PORT", "8883"))
MQTT_USER  = get_secret("MQTT_USER",  "logistica123")
MQTT_PASS  = get_secret("MQTT_PASS",  "Logistica1")
TOPIC_PUB  = "almacen/escaneo"
TOPIC_SUB  = "almacen/confirmacion"
TOPIC_AUTH = "almacen/rfid"

# ── Seguridad ─────────────────────────────────────────────────
_uids_raw        = get_secret("UIDS_AUTORIZADOS", "07:A5:FF:0606:7F:04:07,92:D1:10:06")
UIDS_AUTORIZADOS = set(u.strip().upper() for u in _uids_raw.split(",") if u.strip())
PASSWORD_ACCESO  = get_secret("PASSWORD_ACCESO", "1234567890")  # Operador
PASSWORD_ADMIN   = get_secret("PASSWORD_ADMIN",  "1020304050")  # Administrador

# ── Constantes estructurales del almacen ─────────────────────
CARGA_MAX_NIVEL = 2000.0
PESO_SOBRE      = 2000.0
ALTO_LIBRE      = 1.00
ALTO_MAX_N1_N2  = 1.50
ALTO_MAX_N3     = 1.80
NUM_PISOS       = 5
NUM_NIVELES     = 3
NUM_COLS        = 3

TIPOS_EMBALAJE = [
    "Pallet americano (1219x1016 mm)",
    "Pallet europeo / EUR (1200x800 mm)",
    "Pallet industrial (1200x1000 mm)",
    "Pallet semilla (1200x1200 mm)",
    "Personalizado",
]

ZONA_A_RACK = {
    "FILA A": "POS_1",
    "FILA B": "POS_2",
    "FILA C": "POS_3",
    "FILA D": "POS_4",
    "SOBREDIMENSIONES": "POS_5",
}

# ── Tokens de sesion ─────────────────────────────────────────
import hashlib
TOKEN_OPERADOR = hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16] + '_operador'
TOKEN_ADMIN    = hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16] + '_admin'
TOKEN_ADMIN_2  = hashlib.sha256(PASSWORD_ADMIN.encode()).hexdigest()[:16]  + '_admin'
