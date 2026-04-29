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
st.set_page_config(page_title="WMS Cloud", layout="wide")

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
    'navigate_to_gemelo': False,
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

# ── Polling confirmacion PTL — auto-confirm via sensor CNY70 ──────
# Los botones físicos fueron reemplazados por sensores CNY70.
# Cuando cualquier sensor del rack pendiente reporta "ocupado",
# se confirma automáticamente el depósito.
_SENSOR_RACK_MAP = {'RACK_1': 'R1', 'RACK_2': 'R2', 'RACK_3': 'R3', 'RACK_4': 'R4'}

if st.session_state.get("confirmacion_pendiente"):
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=2000, key="ptl_confirm_refresh")
    try:
        from firebase import leer_sensores
        _sensores = leer_sensores()
        _rack_pend = st.session_state.confirmacion_pendiente
        _prefijo   = _SENSOR_RACK_MAP.get(_rack_pend)
        if _prefijo and _sensores:
            for _lbl, _sdata in _sensores.items():
                if _lbl.startswith(_prefijo) and isinstance(_sdata, dict):
                    if _sdata.get('estado') == 'ocupado':
                        st.session_state.confirmacion_pendiente = None
                        st.session_state.rack_resaltado         = None
                        st.session_state.ultima_ubicacion       = None
                        print(f"[SENSOR] Auto-confirmado por {_lbl}")
                        st.rerun()
                        break
    except Exception as _e:
        print(f"[SENSOR] Error en auto-confirm: {_e}")

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

st.session_state.pop('_pwd_bienvenido', None)  # consumido — saludo va en sidebar

# ── Sidebar ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("<h2 style='margin:0;padding:0;'>WMS</h2>", unsafe_allow_html=True)

    _rol     = st.session_state.get('rol', 'operador')
    _color   = '#F59E0B' if _rol == 'admin' else '#48484A'
    _emp_sb  = st.session_state.get('_empleado_activo') or {}
    _hon_sb  = _emp_sb.get('honorifico', '')
    _ape_sb  = _emp_sb.get('apellido', '')
    if _ape_sb:
        _ape_part = _ape_sb.split()[0]
        _saludo_sb = f"{_hon_sb} {_ape_part}".strip() if _hon_sb else _ape_part
    else:
        _saludo_sb = 'Administrador' if _rol == 'admin' else 'Operador'

    st.markdown(
        f"<div style='margin-top:6px;margin-bottom:2px;'>"
        f"  <div style='color:#E5E5EA;font-size:15px;font-weight:700;line-height:1.3;'>{_saludo_sb}</div>"
        f"  <div style='font-size:13px;color:{_color};margin-top:3px;'>"
        f"    Rol: <b>{'Administrador' if _rol == 'admin' else 'Operador'}</b>"
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
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
        with st.expander(f"Reorden — {len(_alertas_s)} art.", expanded=False):
            for _k, _v in _alertas_s:
                st.markdown(
                    f"**{_v.get('nombre','N/A')}**  \n"
                    f"SKU: `{_v.get('sku_base','N/A')}` · "
                    f"Stock: **{_v.get('cantidad',1)}** / Mín: {_v.get('stock_minimo',0)}  \n"
                    f"Rack: {_v.get('rack','')} · P{_v.get('piso','')} · "
                    f"N{_v.get('fila','')} · C{_v.get('columna','')}"
                )
                st.divider()

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
/* ── Paleta global ───────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > div:first-child {
    background-color: #111113 !important;
}
[data-testid="stSidebar"] {
    background-color: #1C1C1E !important;
    border-right: 1px solid rgba(72,72,74,0.35) !important;
}
[data-testid="stSidebar"] * { color: #E5E5EA !important; }

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background-color: #1C1C1E !important;
    border-bottom: 1px solid #48484A !important;
    gap: 16px !important;
    padding: 0 8px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: #F59E0B !important;
    background-color: transparent !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #E5E5EA !important;
    border-bottom: 2px solid #48484A !important;
    background-color: rgba(72,72,74,0.12) !important;
}

/* Botones */
[data-testid="stButton"] > button {
    background-color: #1C1C1E !important;
    color: #E5E5EA !important;
    border: 1px solid #48484A !important;
    border-radius: 8px !important;
    transition: background 0.2s, border-color 0.2s !important;
}
[data-testid="stButton"] > button:hover {
    background-color: #48484A !important;
    border-color: #F59E0B !important;
}
[data-testid="stButton"] > button[kind="primary"] {
    background-color: #48484A !important;
    border-color: #48484A !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background-color: #F59E0B !important;
    color: #1C1C1E !important;
}

/* Inputs de texto y número */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input {
    background-color: #1C1C1E !important;
    color: #E5E5EA !important;
    border-color: #48484A !important;
    border-radius: 8px !important;
}
[data-testid="stTextInput"] input::placeholder,
[data-testid="stNumberInput"] input::placeholder { color: #F59E0B !important; }
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label { color: #F59E0B !important; }

/* Selectbox */
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background-color: #1C1C1E !important;
    border-color: #48484A !important;
    border-radius: 8px !important;
}
[data-testid="stSelectbox"] label { color: #F59E0B !important; }

/* Métricas */
[data-testid="stMetric"] label      { color: #F59E0B !important; }
[data-testid="stMetricValue"]        { color: #E5E5EA !important; }
[data-testid="stMetricDelta"]        { color: #F59E0B !important; }

/* Captions y texto secundario */
[data-testid="stCaptionContainer"] p { color: #F59E0B !important; }

/* Expander general */
[data-testid="stExpander"] summary   { color: #F59E0B !important; }
[data-testid="stExpander"] summary svg { fill: #F59E0B !important; }

/* Expander de reorden en sidebar — ámbar */
[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(245,158,11,0.08) !important;
    border: 1px solid rgba(245,158,11,0.35) !important;
    border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: #fbbf24 !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
    fill: #fbbf24 !important;
}

/* Divider */
hr { border-color: rgba(72,72,74,0.35) !important; }

/* DataFrame */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(72,72,74,0.4) !important;
    border-radius: 8px !important;
}

/* ── Rack layout helpers ─────────────────────────────── */
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
    "<h1 style='text-align:center;color:#E5E5EA;margin-bottom:4px;letter-spacing:1px;'>"
    "Warehouse Management System</h1>",
    unsafe_allow_html=True
)


# ── Detección automática de dispositivo ──────────────────────
import re as _re
if 'movil' not in st.query_params:
    _ua = st.context.headers.get('User-Agent', '')
    _auto_movil = bool(_re.search(r'Android|iPhone|iPad|iPod|Mobile', _ua, _re.IGNORECASE))
    st.query_params['movil'] = '1' if _auto_movil else '0'

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

# ── Banner confirmación pendiente ─────────────────────────────
if st.session_state.confirmacion_pendiente:
    _ub = st.session_state.get('ultima_ubicacion', {})
    _rack = st.session_state.confirmacion_pendiente

    # Mapa fila legible
    _fila_nombres = {'RACK_1':'FILA A','RACK_2':'FILA B','RACK_3':'FILA C','RACK_4':'FILA D','RACK_5':'SOBREDIMENSIONES'}
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
        f"<div style='color:#8892b0;font-size:11px;margin-top:4px;'>{'Dirígete a la ubicación indicada y deposita el pallet — el sistema confirmará automáticamente.' if _es_movil else 'LED encendido en panel — El sensor confirmará automáticamente al detectar el pallet.'}</div>"
        f"</div>",
        unsafe_allow_html=True
    )
    if st.button(f"CONFIRMAR MANUALMENTE — {_fila}", type="secondary", use_container_width=True):
        st.session_state.confirmacion_pendiente = None
        st.session_state.rack_resaltado = None
        st.rerun()
    st.divider()

# ── Navegación post-registro ──────────────────────────────────
if st.session_state.get('navigate_to_gemelo'):
    st.session_state.navigate_to_gemelo = False
    _components.html("""<script>
setTimeout(function(){
    var tabs=window.parent.document.querySelectorAll('[data-baseweb="tab"]');
    if(tabs.length>0) tabs[0].click();
},350);
</script>""", height=0)

# ── Renderizar según dispositivo ──────────────────────────────
if not _es_movil:
    _tab_labels = ['RASTREO Y UBICACIÓN', 'MAESTRO DE ARTICULOS']
    if st.session_state.get('rol') == 'admin':
        _tab_labels.append('EMPLEADOS')
    tabs = st.tabs(_tab_labels)
    with tabs[0]:
        from ui.gemelo import render as render_gemelo
        render_gemelo(_TOK_ACTIVO)
    with tabs[1]:
        from ui.maestro import render as render_maestro
        render_maestro()
    if len(tabs) > 2:
        with tabs[2]:
            from ui.empleados import render as render_empleados
            render_empleados()
else:
    st.markdown("""<style>
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    position: fixed !important;
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 9999 !important;
    background: #1C1C1E !important;
    border-top: 1px solid rgba(72,72,74,0.45) !important;
    border-bottom: none !important;
    padding: 6px 12px env(safe-area-inset-bottom,8px) !important;
    gap: 8px !important;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.4) !important;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    flex: 1 !important;
    justify-content: center !important;
    padding: 12px 4px !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 13px !important;
    letter-spacing: 0.8px !important;
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] {
    background: rgba(72,72,74,0.22) !important;
    border: 1px solid #48484A !important;
    border-bottom: 1px solid #48484A !important;
    color: #E5E5EA !important;
}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="false"] {
    background: transparent !important;
    border: 1px solid transparent !important;
    color: #F59E0B !important;
}
.main .block-container { padding-bottom: 90px !important; }
</style>""", unsafe_allow_html=True)

    tab_esc, tab_alt = st.tabs(['ESCÁNER', 'ALTA'])
    with tab_esc:
        from ui.escaner import render_escaner
        render_escaner()
    with tab_alt:
        from ui.escaner import render_alta
        render_alta()
