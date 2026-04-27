"""
firebase.py — Operaciones con Firebase Realtime Database.
Usa cache de session_state para minimizar llamadas HTTP.
"""
import requests
import datetime
import streamlit as st
from config import FIREBASE_URL, HISTORIAL_URL, RFID_URL, SENSORES_URL

# ── Base de datos principal ───────────────────────────────────

@st.cache_data(ttl=4, show_spinner=False)
def _fetch_firebase():
    """Llamada real a Firebase. Cacheada 4 segundos por st.cache_data."""
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception:
        pass
    return {}

def cargar_db(forzar=False):
    """
    Devuelve la DB. Usa cache de session_state como primera capa
    y st.cache_data como segunda capa (4s TTL).
    forzar=True salta el cache de session_state.
    """
    if not forzar and st.session_state.get('db') is not None:
        return st.session_state.db
    db = _fetch_firebase()
    st.session_state.db = db
    return db

def guardar_db(db):
    """Escribe en Firebase y actualiza ambos caches."""
    try:
        requests.put(FIREBASE_URL, json=db, timeout=5)
        st.session_state.db = db
        _fetch_firebase.clear()  # limpiar cache para el proximo fetch
    except Exception as e:
        st.error(f"Error al guardar en Firebase: {e}")

# ── Historial ─────────────────────────────────────────────────

def registrar_movimiento(accion, uid, detalle='', rol=None):
    """Guarda un evento en /historial. No bloquea si falla."""
    try:
        res = requests.get(HISTORIAL_URL, timeout=5)
        historial = res.json() if res.status_code == 200 and res.json() else {}
        ts  = datetime.datetime.now()
        key = ts.strftime('%Y%m%d_%H%M%S_') + uid[:8].replace('-', '_')
        historial[key] = {
            'accion':    accion,
            'uid':       uid,
            'detalle':   detalle,
            'rol':       rol or st.session_state.get('rol', 'operador'),
            'timestamp': ts.strftime('%Y-%m-%d %H:%M:%S'),
        }
        requests.put(HISTORIAL_URL, json=historial, timeout=5)
    except Exception:
        pass

def cargar_historial():
    """Lee el historial completo de Firebase."""
    try:
        res = requests.get(HISTORIAL_URL, timeout=5)
        return res.json() if res.status_code == 200 and res.json() else {}
    except Exception:
        return {}

def limpiar_historial():
    """Borra todo el historial."""
    try:
        requests.put(HISTORIAL_URL, json={}, timeout=5)
    except Exception:
        pass

# ── RFID pendiente ────────────────────────────────────────────

@st.cache_data(ttl=2, show_spinner=False)
def _fetch_sensores():
    try:
        res = requests.get(SENSORES_URL, timeout=3)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception:
        pass
    return {}


def leer_sensores():
    """Lee /almacen/sensores. Retorna {label: {estado, ts}}. Cache 2s."""
    return _fetch_sensores()


def leer_rfid_pendiente():
    """
    Lee el nodo rfid_pendiente de Firebase.
    Retorna el UID si es reciente (< 10 segundos), None si no.
    """
    import time
    try:
        res = requests.get(RFID_URL, timeout=3)
        data = res.json() if res.status_code == 200 and res.json() else None
        if data and isinstance(data, dict):
            uid = data.get('uid', '').strip().upper()
            ts  = data.get('ts', 0)
            if uid and (time.time() - ts) < 10:
                # Limpiar para no reprocesar
                requests.put(RFID_URL, json=None, timeout=3)
                return uid
    except Exception:
        pass
    return None
