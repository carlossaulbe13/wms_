"""
app.py — Punto de entrada del UMAD WMS.
Orquesta los modulos: config, firebase, mqtt_client, logica, ui/*
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import streamlit.components.v1 as _components
import hashlib
import time

# ── Modulos propios ───────────────────────────────────────────
from config import (
    TOKEN_OPERADOR, TOKEN_ADMIN, TOKEN_ADMIN_2,
    PASSWORD_ACCESO, PASSWORD_ADMIN,
)
from firebase import cargar_db
from mqtt_client import init_mqtt

# ── Configuracion de pagina ───────────────────────────────────
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")

# ── Inicializar MQTT una sola vez (cache_resource) ────────────
_mqtt = init_mqtt()
if _mqtt and 'mqtt_client' not in st.session_state:
    st.session_state.mqtt_client = _mqtt

# ── Defaults de session_state ─────────────────────────────────
_defaults = {
    'db': None,
    'sku_pendiente': None,
    'ultimo_sku_procesado': None,
    'confirmacion_pendiente': None,
    'qr_generado': None,
    'twin_zona': None,
    'twin_fila': None,
    'twin_rack': None,
    'rack_resaltado': None,
    'rack_resaltado_ts': 0.0,
    'es_movil': None,
    'msg_mqtt_recibido': None,
    'uid_rfid_recibido': None,
    # Autenticacion
    'autenticado': False,
    'rol': 'operador',
    'intentos_password': 0,
    'bloqueado_hasta': 0.0,
    'session_token': None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Carga inicial de Firebase
if st.session_state.db is None:
    cargar_db(forzar=True)

# Procesar mensajes MQTT acumulados
from mqtt_client import procesar_mensajes_mqtt
procesar_mensajes_mqtt()

# ── Tokens de sesion ─────────────────────────────────────────
_TOKEN_BASE  = hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16]
_TOKEN_ADMIN_PWD = hashlib.sha256(PASSWORD_ADMIN.encode()).hexdigest()[:16]

# ── Restaurar sesion desde query param ───────────────────────
if not st.session_state.get('autenticado'):
    _tok = st.query_params.get('_s', '')
    if _tok in (_TOKEN_BASE + '_admin', _TOKEN_ADMIN_PWD + '_admin'):
        st.session_state.autenticado   = True
        st.session_state.rol           = 'admin'
        st.session_state.session_token = _tok
    elif _tok == _TOKEN_BASE + '_operador':
        st.session_state.autenticado   = True
        st.session_state.rol           = 'operador'
        st.session_state.session_token = _tok

# ── Control de acceso ────────────────────────────────────────
if not st.session_state.get('autenticado', False):
    from ui.login import pantalla_login
    pantalla_login(_TOKEN_BASE, _TOKEN_ADMIN_PWD)
    st.stop()

# Token activo para links de navegacion
_TOK_ACTIVO = st.session_state.get('session_token') or (_TOKEN_BASE + '_operador')

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    # Título más grande
    st.markdown("<h2 style='margin:0;padding:0;'>UMAD WMS</h2>", unsafe_allow_html=True)
    
    _rol = st.session_state.get('rol', 'operador')
    _color = '#22c55e' if _rol == 'admin' else '#8892b0'
    # Texto de rol más grande
    st.markdown(
        f"<div style='font-size:16px;color:{_color};margin-bottom:8px;margin-top:4px;'>"
        f"Rol: <b>{'Administrador' if _rol == 'admin' else 'Operador'}</b></div>",
        unsafe_allow_html=True
    )
    st.markdown("---")

    # Alertas de reorden en sidebar
    _db_s = st.session_state.get('db') or {}
    _alertas_s = [
        (k, v) for k, v in _db_s.items()
        if int(v.get('stock_minimo', 0)) > 0
        and int(v.get('cantidad', 1)) <= int(v.get('stock_minimo', 0))
        and v.get('estado') == 'ACTIVO'
    ]
    if _alertas_s:
        st.markdown(
            f"<div style='background:#7f1d1d;border-radius:8px;padding:8px 12px;"
            f"margin-bottom:8px;font-size:12px;color:#fca5a5;'>"
            f"<b>Reorden:</b> {len(_alertas_s)} articulo(s)</div>",
            unsafe_allow_html=True
        )

    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.autenticado   = False
        st.session_state.rol           = 'operador'
        st.session_state.session_token = None
        st.query_params.clear()
        st.rerun()

    # Toggle modo movil/escritorio
    _es_movil = st.session_state.get('es_movil', False)
    st.caption(f"Modo: {'Movil' if _es_movil else 'Escritorio'}")
    if _es_movil:
        if st.button('Cambiar a escritorio', use_container_width=True):
            st.query_params['movil'] = '0'
            st.rerun()
    else:
        if st.button('Cambiar a movil', use_container_width=True):
            st.query_params['movil'] = '1'
            st.rerun()

# ── CSS global ────────────────────────────────────────────────
st.markdown("""
<style>
div[data-testid="column"] > div { padding: 0 !important; }
.rack-row > div[data-testid="stHorizontalBlock"] { gap: 6px !important; }
.rack-row { margin-bottom: 6px !important; }
div[data-testid="stVerticalBlockBorderWrapper"] { padding: 0 !important; }
div[data-testid="stSelectbox"] input,
div[data-testid="stSelectbox"] input:hover,
div[data-testid="stSelectbox"] input:focus {
    cursor: pointer !important;
    caret-color: transparent !important;
    user-select: none !important;
    color: transparent !important;
    text-shadow: 0 0 0 var(--text-color, #fff) !important;
}
div[data-testid="stSelectbox"] [data-baseweb="select"],
div[data-testid="stSelectbox"] [data-baseweb="select"] * { cursor: pointer !important; }
</style>
""", unsafe_allow_html=True)

# ── Titulo ────────────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;color:#FF4B4B;margin-bottom:4px;'>"
    "UMAD Warehouse Management System</h1>",
    unsafe_allow_html=True
)

# ── Alertas de reorden (banner) ───────────────────────────────
_alertas = [
    (k, v) for k, v in (_db_s.items())
    if int(v.get('stock_minimo', 0)) > 0
    and int(v.get('cantidad', 1)) <= int(v.get('stock_minimo', 0))
    and v.get('estado') == 'ACTIVO'
]
if _alertas:
    with st.expander(f"ALERTA DE REORDEN — {len(_alertas)} articulo(s) bajo minimo", expanded=True):
        for _k, _v in _alertas:
            st.warning(
                f"{_v.get('nombre','N/A')} | SKU: {_v.get('sku_base','N/A')} | "
                f"Stock: {_v.get('cantidad',1)} pzas | Min: {_v.get('stock_minimo',0)} pzas | "
                f"Rack: {_v.get('rack','')} Piso {_v.get('piso','')} Niv {_v.get('fila','')} Col {_v.get('columna','')}"
            )

# ── Banner confirmacion pendiente ─────────────────────────────
if st.session_state.confirmacion_pendiente:
    st.warning(
        f"ACCION REQUERIDA: LED del Rack {st.session_state.confirmacion_pendiente} ENCENDIDO."
    )
    if st.button(f"CONFIRMAR — APAGAR LED DE {st.session_state.confirmacion_pendiente}"):
        from mqtt_client import publicar
        publicar(st.session_state.confirmacion_pendiente, "OFF")
        st.session_state.confirmacion_pendiente = None
        st.rerun()
    st.divider()

# ── Deteccion automatica de dispositivo ──────────────────────
if 'movil' not in st.query_params:
    _components.html("""
    <script>
    const esMov = window.screen.width < 768 ||
                  /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    const url = new URL(window.parent.location.href);
    if (esMov && url.searchParams.get('movil') !== '1') {
        url.searchParams.set('movil', '1');
        window.parent.location.href = url.toString();
    } else if (!esMov && url.searchParams.get('movil') !== '0') {
        url.searchParams.set('movil', '0');
        window.parent.location.href = url.toString();
    }
    </script>
    """, height=0)

_es_movil = st.query_params.get('movil', '0') == '1'
st.session_state.es_movil = _es_movil

# ── Navegacion por query params del gemelo ────────────────────
_qp = dict(st.query_params)
if 'zona' in _qp:
    fila_raw = _qp.get('fila', None)
    st.session_state.twin_zona = _qp['zona']
    st.session_state.twin_fila = fila_raw.replace('+', ' ') if fila_raw else None
    if 'rack' in _qp:
        st.session_state.twin_rack = int(_qp['rack'])
    st.query_params.clear()
    st.query_params['_s'] = _TOK_ACTIVO
    st.rerun()

# ── Renderizar segun dispositivo ──────────────────────────────
if not _es_movil:
    tabs = st.tabs(['GEMELO DIGITAL', 'MAESTRO DE ARTICULOS'])
    with tabs[0]:
        from ui.gemelo import render as render_gemelo
        render_gemelo(_TOK_ACTIVO)
    with tabs[1]:
        from ui.maestro import render as render_maestro
        render_maestro()
else:
    tabs = st.tabs(['ESCANER DE CAMPO', 'ALTA DE MATERIAL'])
    with tabs[0]:
        from ui.escaner import render_escaner
        render_escaner()
    with tabs[1]:
        from ui.escaner import render_alta
        render_alta()
