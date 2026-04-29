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

def _nodo_url(uid: str) -> str:
    """URL del nodo individual de un pallet."""
    return FIREBASE_URL.replace('maestro_articulos.json', f'maestro_articulos/{uid}.json')

def guardar_db(db):
    """Escribe en Firebase y actualiza ambos caches."""
    try:
        res = requests.put(FIREBASE_URL, json=db, timeout=5)
        if res.status_code not in (200, 204):
            st.error(f"Firebase rechazó la escritura: {res.status_code} — {res.text[:200]}")
            return
        st.session_state.db = db
        _fetch_firebase.clear()
    except Exception as e:
        st.error(f"Error al guardar en Firebase: {e}")

def dar_de_baja_pallet(uid: str) -> bool:
    """PATCH sobre el nodo individual: cambia estado a BAJA sin tocar el resto."""
    import datetime as _dt
    payload = {
        'estado':     'BAJA',
        'fecha_baja': _dt.datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    try:
        res = requests.patch(_nodo_url(uid), json=payload, timeout=5)
        if res.status_code not in (200, 204):
            st.error(f"Firebase rechazó la baja: {res.status_code} — {res.text[:200]}")
            return False
        # Actualizar cache local
        db = st.session_state.get('db') or {}
        if uid in db:
            db[uid].update(payload)
            st.session_state.db = db
        _fetch_firebase.clear()
        return True
    except Exception as e:
        st.error(f"Error al dar de baja en Firebase: {e}")
        return False

def eliminar_pallet(uid: str) -> bool:
    """PATCH con null sobre el nodo individual — más compatible que DELETE."""
    try:
        res = requests.patch(FIREBASE_URL, json={uid: None}, timeout=5)
        if res.status_code not in (200, 204):
            st.error(f"Firebase rechazó la eliminación: {res.status_code} — {res.text[:200]}")
            return False
        db = dict(st.session_state.get('db') or {})
        db.pop(uid, None)
        st.session_state.db = db
        _fetch_firebase.clear()
        return True
    except Exception as e:
        st.error(f"Error al eliminar en Firebase: {e}")
        return False

def eliminar_pallets(uids: list) -> int:
    """Elimina múltiples pallets en un solo PATCH."""
    if not uids:
        return 0
    payload = {uid: None for uid in uids}
    try:
        res = requests.patch(FIREBASE_URL, json=payload, timeout=10)
        if res.status_code not in (200, 204):
            st.error(f"Firebase rechazó la eliminación masiva: {res.status_code} — {res.text[:200]}")
            return 0
        db = dict(st.session_state.get('db') or {})
        for uid in uids:
            db.pop(uid, None)
        st.session_state.db = db
        _fetch_firebase.clear()
        return len(uids)
    except Exception as e:
        st.error(f"Error en eliminación masiva: {e}")
        return 0

def vaciar_inventario() -> bool:
    """Borra TODOS los pallets escribiendo null en la raíz del nodo."""
    try:
        res = requests.put(FIREBASE_URL, json=None, timeout=10)
        if res.status_code not in (200, 204):
            st.error(f"Firebase rechazó vaciar inventario: {res.status_code} — {res.text[:200]}")
            return False
        st.session_state.db = {}
        _fetch_firebase.clear()
        return True
    except Exception as e:
        st.error(f"Error al vaciar inventario: {e}")
        return False

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
