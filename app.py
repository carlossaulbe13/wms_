"""
app.py — Punto de entrada del UMAD WMS Cloud
Versión 3.0 - Optimizada y limpia
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import streamlit.components.v1 as _components
import hashlib

import time
import requests as _req_ptl
from config import PASSWORD_ACCESO, PASSWORD_ADMIN
from firebase import cargar_db

# ── Configuracion de pagina ───────────────────────────────────
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")

# ── Defaults de session_state ─────────────────────────────────
_defaults = {
    'db': None,
    'confirmacion_pendiente': None,
    'qr_generado': None,
    'twin_zona': None,
    'twin_fila': None,
    'twin_rack': None,
    'rack_resaltado': None,
    'rack_resaltado_ts': 0.0,
    'es_movil': False,
    'autenticado': False,
    'rol': 'operador',
    'intentos_password': 0,
    'bloqueado_hasta': 0.0,
    'session_token': None,
    'ultima_ubicacion': None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Carga inicial de Firebase
if st.session_state.db is None:
    cargar_db(forzar=True)

# ── Leer confirmacion PTL desde Firebase (cada render) ───────
if st.session_state.get("confirmacion_pendiente"):
    try:
        from config import PTL_CONFIRM_URL
        _r = _req_ptl.get(PTL_CONFIRM_URL, timeout=2)
        _data = _r.json() if _r.status_code == 200 and _r.json() else None
        if _data and isinstance(_data, dict):
            _rack_conf = _data.get("rack", "").strip()
            _ts_conf   = _data.get("ts", 0)
            if _rack_conf and (time.time() - _ts_conf) < 30:
                if _rack_conf == st.session_state.confirmacion_pendiente:
                    st.session_state.confirmacion_pendiente = None
                    st.session_state.rack_resaltado = None
                    _req_ptl.put(PTL_CONFIRM_URL, json=None, timeout=2)
                    print(f"[PTL] Confirmacion recibida: {_rack_conf}")
    except Exception as _e:
        print(f"[PTL] Error leyendo confirmacion: {_e}")

# ── Tokens de sesion ─────────────────────────────────────────
_TOKEN_BASE = hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16]
_TOKEN_ADMIN = hashlib.sha256(PASSWORD_ADMIN.encode()).hexdigest()[:16]

# ── Restaurar sesion desde query param ───────────────────────
if not st.session_state.get('autenticado'):
    _tok = st.query_params.get('_s', '')
    if _tok in (_TOKEN_BASE + '_admin', _TOKEN_ADMIN + '_admin'):
        st.session_state.autenticado = True
        st.session_state.rol = 'admin'
        st.session_state.session_token = _tok
    elif _tok == _TOKEN_BASE + '_operador':
        st.session_state.autenticado = True
        st.session_state.rol = 'operador'
        st.session_state.session_token = _tok

# ── Control de acceso ────────────────────────────────────────
if not st.session_state.get('autenticado', False):
    from ui.login import pantalla_login
    pantalla_login(_TOKEN_BASE, _TOKEN_ADMIN)
    st.stop()

# Token activo para navegación
_TOK_ACTIVO = st.session_state.get('session_token') or (_TOKEN_BASE + '_operador')

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h2 style='margin:0;padding:0;'>UMAD WMS</h2>", unsafe_allow_html=True)
    
    _rol = st.session_state.get('rol', 'operador')
    _color = '#22c55e' if _rol == 'admin' else '#8892b0'
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
        st.session_state.autenticado = False
        st.session_state.rol = 'operador'
        st.session_state.session_token = None
        st.query_params.clear()
        st.rerun()

    # Toggle modo móvil/escritorio
    _es_movil = st.session_state.get('es_movil', False)
    st.caption(f"Modo: {'Móvil' if _es_movil else 'Escritorio'}")
    if _es_movil:
        if st.button(' Cambiar a Escritorio', use_container_width=True, key='btn_escritorio'):
            st.query_params['movil'] = '0'
            st.session_state.es_movil = False
            st.rerun()
    else:
        if st.button(' Cambiar a Móvil', use_container_width=True, key='btn_movil'):
            st.query_params['movil'] = '1'
            st.session_state.es_movil = True
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

# ── Título ────────────────────────────────────────────────────
st.markdown(
    "<h1 style='text-align:center;color:#FF4B4B;margin-bottom:4px;'>"
    "UMAD Warehouse Management System</h1>",
    unsafe_allow_html=True
)

# ── Alertas de reorden (banner) ───────────────────────────────
if _alertas_s:
    with st.expander(f"ALERTA DE REORDEN — {len(_alertas_s)} articulo(s) bajo mínimo", expanded=True):
        for _k, _v in _alertas_s:
            st.warning(
                f"{_v.get('nombre','N/A')} | SKU: {_v.get('sku_base','N/A')} | "
                f"Stock: {_v.get('cantidad',1)} pzas | Mín: {_v.get('stock_minimo',0)} pzas | "
                f"Rack: {_v.get('rack','')} Piso {_v.get('piso','')} Niv {_v.get('fila','')} Col {_v.get('columna','')}"
            )

# ── Banner confirmación pendiente ─────────────────────────────
if st.session_state.confirmacion_pendiente:
    _ub = st.session_state.get('ultima_ubicacion', {})
    _rack = st.session_state.confirmacion_pendiente

    # Mapa fila legible
    _fila_nombres = {'POS_1':'FILA A','POS_2':'FILA B','POS_3':'FILA C','POS_4':'FILA D','POS_5':'SOBREDIMENSIONES'}
    _fila = _fila_nombres.get(_rack, _rack)

    st.markdown(
        f"<div style='background:#713f12;border:2px solid #facc15;border-radius:10px;"
        f"padding:16px 20px;margin-bottom:12px;'>"
        f"<div style='color:#facc15;font-size:13px;font-weight:700;letter-spacing:1px;"
        f"margin-bottom:10px;'>MATERIAL ASIGNADO — ACCION REQUERIDA</div>"
        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:12px;'>"
        f"<div style='background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;text-align:center;'>"
        f"<div style='color:#8892b0;font-size:10px;'>FILA</div>"
        f"<div style='color:#facc15;font-size:18px;font-weight:700;'>{_fila}</div></div>"
        f"<div style='background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;text-align:center;'>"
        f"<div style='color:#8892b0;font-size:10px;'>RACK</div>"
        f"<div style='color:#facc15;font-size:18px;font-weight:700;'>{'R'+str(_ub.get('piso','?')) if _ub else '?'}</div></div>"
        f"<div style='background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;text-align:center;'>"
        f"<div style='color:#8892b0;font-size:10px;'>NIVEL</div>"
        f"<div style='color:#facc15;font-size:18px;font-weight:700;'>{_ub.get('nivel','?') if _ub else '?'}</div></div>"
        f"<div style='background:rgba(0,0,0,0.3);border-radius:6px;padding:8px;text-align:center;'>"
        f"<div style='color:#8892b0;font-size:10px;'>COLUMNA</div>"
        f"<div style='color:#facc15;font-size:18px;font-weight:700;'>{_ub.get('col','?') if _ub else '?'}</div></div>"
        f"</div>"
        f"<div style='color:#cdd3ea;font-size:12px;'>"
        f"<b>{_ub.get('nombre','') if _ub else ''}</b>"
        f"{'  |  SKU: ' + _ub.get('sku','') if _ub and _ub.get('sku') else ''}"
        f"</div>"
        f"<div style='color:#8892b0;font-size:11px;margin-top:4px;'>LED encendido en panel — Confirma depositando el material</div>"
        f"</div>",
        unsafe_allow_html=True
    )
    if st.button(f"CONFIRMAR DEPOSITO — APAGAR LED {_fila}", type="primary", use_container_width=True):
        st.session_state.confirmacion_pendiente = None
        st.session_state.rack_resaltado = None
        st.rerun()
    st.divider()

# ── Detección automática de dispositivo ──────────────────────
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

# ── Navegación por query params del gemelo ────────────────────
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

# ── Renderizar según dispositivo ──────────────────────────────
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
