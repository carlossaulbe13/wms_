import streamlit as st
import paho.mqtt.client as mqtt
import requests
import cv2
import numpy as np
import pandas as pd
from pyzbar.pyzbar import decode
import qrcode
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
from streamlit_autorefresh import st_autorefresh
import time
import os

# ─────────────────────────────────────────
# CONFIGURACION — lee de st.secrets (Streamlit Cloud)
# o de variables de entorno locales (.env)
# ─────────────────────────────────────────
def get_secret(key, default=""):
    """Lee primero de st.secrets (Cloud), luego de env, luego default."""
    try:
        return st.secrets[key]
    except Exception:
        return os.environ.get(key, default)

# Cargar .env solo si existe (desarrollo local)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────
# CONFIGURACION FIREBASE
# ─────────────────────────────────────────
FIREBASE_URL = get_secret("FIREBASE_URL", "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json")

def cargar_db():
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except Exception as e:
        st.error(f"ERROR DE CONEXION CON FIREBASE: {e}")
    return {}

def guardar_db(db):
    try:
        requests.put(FIREBASE_URL, json=db, timeout=5)
    except Exception as e:
        st.error(f"ERROR AL GUARDAR EN FIREBASE: {e}")

# ─────────────────────────────────────────
# CONFIGURACION MQTT
# ─────────────────────────────────────────
MQTT_HOST  = get_secret("MQTT_HOST",  "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud")
MQTT_PORT  = int(get_secret("MQTT_PORT", "8883"))
MQTT_USER  = get_secret("MQTT_USER",  "saul_mqtt")
MQTT_PASS  = get_secret("MQTT_PASS",  "135700/Saul")
TOPIC_PUB  = "almacen/escaneo"
TOPIC_SUB  = "almacen/confirmacion"
TOPIC_AUTH = "almacen/rfid"

# ─── Seguridad ───────────────────────────────────────────
# UIDs autorizados: agrega aqui los de tus tarjetas/llaveros
# Para conocer el UID de una tarjeta nueva, activa modo debug en el .ino
# UIDs desde .env separados por coma: UID1,UID2
_uids_raw = get_secret("UIDS_AUTORIZADOS", "06:7F:04:07,92:D1:10:06")
UIDS_AUTORIZADOS = set(u.strip().upper() for u in _uids_raw.split(",") if u.strip())
PASSWORD_ACCESO  = get_secret("PASSWORD_ACCESO", "1234567890")

if 'msg_mqtt_recibido' not in st.session_state:
    st.session_state.msg_mqtt_recibido = None

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    if payload.endswith("_OFF"):
        st.session_state.msg_mqtt_recibido = payload.replace("_OFF", "")
    elif msg.topic == TOPIC_AUTH:
        # El ESP32 publica el UID leido, lo guardamos para procesarlo en el render
        st.session_state.uid_rfid_recibido = payload.strip().upper()

# ─────────────────────────────────────────────────────────────
# CONSTANTES ESTRUCTURALES DEL ALMACEN
# ─────────────────────────────────────────────────────────────
CARGA_MAX_NIVEL  = 2000.0  # kg máximos por nivel de rack
PESO_SOBRE       = 2000.0  # pallet que supere esto → sobredimensiones

# Reglas de altura por nivel (en metros):
#   nivel 1 y 2 → máx 1.50 m
#   nivel 3      → máx 1.80 m
#   > 1.80 m     → sobredimensiones
ALTO_LIBRE       = 1.00    # < 1 m: bajo, puede ir en cualquier nivel
ALTO_MAX_N1_N2   = 1.50    # niveles 1 y 2 aceptan hasta 1.50 m
ALTO_MAX_N3      = 1.80    # nivel 3 acepta hasta 1.80 m
                            # > 1.80 m → sobredimensiones

NUM_PISOS        = 5
NUM_NIVELES      = 3
NUM_COLS         = 3

# Tipos de embalaje disponibles
TIPOS_EMBALAJE = [
    "Pallet americano (1219×1016 mm)",
    "Pallet europeo / EUR (1200×800 mm)",
    "Pallet industrial (1200×1000 mm)",
    "Pallet semilla (1200×1200 mm)",
    "Caja de carton",
    "Granel / sin embalaje",
    "Personalizado",
]

def peso_en_nivel(db, rack, piso, nivel):
    return sum(
        v.get('peso', 0)
        for v in db.values()
        if v.get('rack') == rack
        and v.get('piso') == piso
        and v.get('fila') == nivel
    )

def nivel_acepta_altura(nivel, alto_m):
    """True si el nivel puede alojar un artículo de alto_m metros."""
    if alto_m <= ALTO_LIBRE:
        return True          # artículo bajo: cualquier nivel
    if nivel in (1, 2):
        return alto_m <= ALTO_MAX_N1_N2
    if nivel == 3:
        return alto_m <= ALTO_MAX_N3
    return False

def asignar_rack_por_peso_vol(peso, vol):
    """Rack según peso/volumen. La altura se evalúa aparte."""
    if peso > PESO_SOBRE:
        return "POS_5"
    if peso >= 100:
        return "POS_4"
    if vol > 1.5:
        return "POS_5"
    if peso >= 50 or vol > 1.0:
        return "POS_3"
    if peso >= 20 or vol > 0.5:
        return "POS_2"
    return "POS_1"

def obtener_coordenada_libre(db, rack_objetivo, peso_nuevo=0, alto_m=0):
    """
    Busca el primer espacio libre respetando:
      - Carga máxima por nivel (CARGA_MAX_NIVEL)  — no aplica en POS_5
      - Restricción de altura por nivel            — no aplica en POS_5
    Orden: piso → nivel (1→3) → columna
    """
    es_sobre = rack_objetivo == "POS_5"
    ocupadas = {
        (v.get('piso'), v.get('fila'), v.get('columna'))
        for v in db.values()
        if v.get('rack') == rack_objetivo
    }
    for p in range(1, NUM_PISOS + 1):
        for niv in range(1, NUM_NIVELES + 1):
            if not es_sobre and not nivel_acepta_altura(niv, alto_m):
                continue
            if not es_sobre:
                carga_actual = peso_en_nivel(db, rack_objetivo, p, niv)
                if carga_actual + peso_nuevo > CARGA_MAX_NIVEL:
                    continue
            for c in range(1, NUM_COLS + 1):
                if (p, niv, c) not in ocupadas:
                    return p, niv, c
    return None, None, None

# ─────────────────────────────────────────
# INICIALIZACION DE ESTADOS
# ─────────────────────────────────────────
defaults = {
    'db': None,
    'sku_pendiente': None,
    'ultimo_sku_procesado': None,
    'confirmacion_pendiente': None,
    'qr_generado': None,
    'twin_zona': None,
    'twin_fila': None,
    'rack_resaltado': None,
    'rack_resaltado_ts': 0.0,
    'es_movil': None,           # None = aun no detectado
    # Autenticacion
    'autenticado': False,
    'uid_rfid_recibido': None,
    'intentos_password': 0,
    'bloqueado_hasta': 0.0,
    'session_token': None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.db is None:
    st.session_state.db = cargar_db()

# ─────────────────────────────────────────
# CONEXION MQTT
# ─────────────────────────────────────────
if 'mqtt_client' not in st.session_state:
    client = mqtt.Client()
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.tls_set()
    client.on_message = on_message
    try:
        client.connect(MQTT_HOST, MQTT_PORT)
        client.subscribe(TOPIC_SUB)
        client.subscribe(TOPIC_AUTH)
        client.loop_start()
        st.session_state.mqtt_client = client
    except Exception:
        st.session_state.mqtt_client = None

if st.session_state.msg_mqtt_recibido:
    if st.session_state.confirmacion_pendiente == st.session_state.msg_mqtt_recibido:
        st.session_state.confirmacion_pendiente = None
    st.session_state.msg_mqtt_recibido = None

# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
ZONA_A_RACK = {
    "FILA A": "POS_1",
    "FILA B": "POS_2",
    "FILA C": "POS_3",
    "FILA D": "POS_4",
    "SOBREDIMENSIONES": "POS_5",
}

def rack_stats(db, rack):
    items = [v for v in db.values() if v.get('rack') == rack]
    congelados = sum(1 for v in items if v.get('estado') == 'CONGELADO')
    return len(items), congelados

def color_celda(item, buscado=False):
    if buscado:
        return "#cce5ff", "#004085"
    if item is None:
        return "#d4edda", "#28a745"
    if item.get('estado') == 'CONGELADO':
        return "#f8d7da", "#dc3545"
    return "#fff3cd", "#ffc107"

# Estilo base para todas las celdas del gemelo — altura fija, sin huecos
CELDA_STYLE = (
    "border-radius:8px; padding:8px 6px; text-align:center; color:black;"
    "height:130px; width:100%; display:flex; flex-direction:column;"
    "justify-content:center; align-items:center; overflow:hidden;"
    "box-sizing:border-box; margin:0px 0px 6px 0px;"
)

# ─────────────────────────────────────────
# PAGINA
# ─────────────────────────────────────────
st.set_page_config(page_title="UMAD WMS Cloud", layout="wide")

# ─────────────────────────────────────────────────────────────
# AUTENTICACION — RFID o contraseña
# ─────────────────────────────────────────────────────────────
def pantalla_login():
    """Muestra la pantalla de login. Retorna True si se concede acceso."""

    # Procesar UID recibido por MQTT (tarjeta acercada al lector)
    uid_entrante = st.session_state.get('uid_rfid_recibido')
    if uid_entrante:
        st.session_state.uid_rfid_recibido = None  # consumir
        if uid_entrante in UIDS_AUTORIZADOS:
            st.session_state.autenticado       = True
            st.session_state.intentos_password = 0
            st.session_state.session_token     = _TOKEN_SECRETO
            st.query_params['_s'] = _TOKEN_SECRETO
            st.rerun()
        else:
            st.session_state.intentos_password += 1

    # Bloqueo por intentos fallidos (3 intentos → 30 segundos)
    bloqueado_hasta = st.session_state.get('bloqueado_hasta', 0.0)
    segundos_restantes = bloqueado_hasta - time.time()
    if segundos_restantes > 0:
        st.markdown("""
        <div style='max-width:420px;margin:10vh auto;background:#1e1e2e;
             border:1.5px solid #dc3545;border-radius:14px;padding:40px 36px;text-align:center;'>
          <div style='font-size:36px;margin-bottom:12px;'></div>
          <h2 style='color:#ef4444;margin-bottom:8px;'>Acceso bloqueado</h2>
          <p style='color:#8892b0;font-size:13px;'>Demasiados intentos fallidos.<br>
          Intenta de nuevo en <b style='color:#cdd3ea;'>{:.0f} segundos</b>.</p>
        </div>""".format(segundos_restantes), unsafe_allow_html=True)
        st_autorefresh(interval=1000, key='bloqueo_refresh')
        return False

    # UI de login
    st.markdown("""
    <div style='max-width:420px;margin:8vh auto 0;text-align:center;'>
      <h1 style='color:#FF4B4B;font-size:26px;margin-bottom:4px;'>UMAD WMS</h1>
      <p style='color:#8892b0;font-size:13px;margin-bottom:32px;'>Warehouse Management System</p>
    </div>""", unsafe_allow_html=True)

    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        # Panel RFID
        rfid_activo = uid_entrante and uid_entrante not in UIDS_AUTORIZADOS
        st.markdown("""
        <div style='background:#16192a;border:1.5px solid #3a3f55;border-radius:12px;
             padding:28px 24px;text-align:center;margin-bottom:16px;'>
          <div style='font-size:40px;margin-bottom:10px;'></div>
          <p style='color:#cdd3ea;font-size:14px;font-weight:600;margin-bottom:4px;'>
            Acerca tu tarjeta RFID al lector</p>
          <p style='color:#8892b0;font-size:11px;'>El lector esta conectado al ESP32</p>
        </div>""", unsafe_allow_html=True)

        if rfid_activo:
            st.error(f"UID no autorizado: {uid_entrante}")

        st.markdown("<p style='text-align:center;color:#8892b0;font-size:12px;margin:8px 0;'>"
                    "— o ingresa tu contrasena —</p>", unsafe_allow_html=True)

        with st.form("login_form"):
            pwd = st.text_input("Contrasena", type="password",
                               placeholder="Ingresa la contrasena de acceso")
            submitted = st.form_submit_button("Entrar", use_container_width=True)
            if submitted:
                if pwd == PASSWORD_ACCESO:
                    st.session_state.autenticado       = True
                    st.session_state.intentos_password = 0
                    st.session_state.session_token     = _TOKEN_SECRETO
                    st.query_params['_s'] = _TOKEN_SECRETO
                    st.rerun()
                else:
                    st.session_state.intentos_password += 1
                    intentos = st.session_state.intentos_password
                    if intentos >= 3:
                        st.session_state.bloqueado_hasta = time.time() + 30
                        st.rerun()
                    else:
                        st.error(f"Contrasena incorrecta. Intento {intentos}/3.")
    return False

# ── Control de acceso global ──────────────────────────────
import hashlib as _hashlib
_TOKEN_SECRETO = _hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16]

# Si el session_state se reseteo (reload por query param),
# restaurar la sesion verificando el token en la URL
if not st.session_state.get('autenticado'):
    _token_url = st.query_params.get('_s', '')
    if _token_url == _TOKEN_SECRETO:
        st.session_state.autenticado   = True
        st.session_state.session_token = _TOKEN_SECRETO

if not st.session_state.get('autenticado', False):
    pantalla_login()
    st.stop()

# Botón de cerrar sesión (esquina superior derecha)
with st.sidebar:
    st.markdown("### UMAD WMS")
    st.markdown("---")
    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.autenticado   = False
        st.session_state.session_token = None
        st.query_params.clear()
        st.rerun()

# CSS global: elimina el gap interno de Streamlit en las columnas marcadas con .rack-grid
st.markdown("""
<style>
/* Elimina el gap horizontal entre columnas en las grillas de racks */
div[data-testid="column"] > div {
    padding: 0 !important;
}
.rack-row > div[data-testid="stHorizontalBlock"] {
    gap: 6px !important;
}
/* Elimina margen extra entre filas de celdas */
.rack-row {
    margin-bottom: 6px !important;
}
/* Asegura que el contenido del column no tenga padding lateral */
div[data-testid="stVerticalBlockBorderWrapper"] {
    padding: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align:center;color:#FF4B4B;margin-bottom:4px;'>"
    "UMAD Warehouse Management System</h1>",
    unsafe_allow_html=True
)

# Banner de confirmacion pendiente
if st.session_state.confirmacion_pendiente:
    st.warning(
        f"ACCION REQUERIDA: El LED del Rack {st.session_state.confirmacion_pendiente} "
        f"esta ENCENDIDO. Confirma fisicamente o hazlo aqui:"
    )
    if st.button(
        f"CONFIRMAR MANUALMENTE — APAGAR LED DE {st.session_state.confirmacion_pendiente}"
    ):
        if st.session_state.mqtt_client:
            st.session_state.mqtt_client.publish(
                TOPIC_PUB, f"{st.session_state.confirmacion_pendiente}_OFF"
            )
        st.session_state.confirmacion_pendiente = None
        st.rerun()
    st.divider()

# ── Deteccion automatica de dispositivo ──────────────────
# Usa st.components para leer ancho de pantalla y escribir query param
import streamlit.components.v1 as _components

# Solo ejecutar deteccion si aun no tenemos el param
if 'movil' not in st.query_params:
    _components.html("""
    <script>
    // Detecta por ancho de pantalla (< 768px = movil)
    // y por user agent como respaldo
    const esMov = window.screen.width < 768 ||
                  /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

    // Comunicar al padre de Streamlit via URL
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

# Leer query param (default: escritorio)
qp_device = st.query_params.get('movil', '0')
es_movil   = qp_device == '1'
st.session_state.es_movil = es_movil

# Indicador y toggle manual en sidebar
with st.sidebar:
    st.caption(f"Modo: {'Movil' if es_movil else 'Escritorio'}")
    if es_movil:
        if st.button('Cambiar a escritorio', use_container_width=True):
            st.query_params['movil'] = '0'
            st.rerun()
    else:
        if st.button('Cambiar a movil', use_container_width=True):
            st.query_params['movil'] = '1'
            st.rerun()

# ── Pestanas segun dispositivo ────────────────────────────
if es_movil:
    tabs = st.tabs(['ESCANER DE CAMPO', 'ALTA DE MATERIAL'])
    tabs_movil = True
else:
    tabs = st.tabs(['GEMELO DIGITAL', 'MAESTRO DE ARTICULOS'])
    tabs_movil = False

# ══════════════════════════════════════════════════════════════
if not tabs_movil:
    with tabs[0]:
        st_autorefresh(interval=4000, key="twin_refresh")
        db = cargar_db()
        st.session_state.db = db

        # Calculos (necesarios para el layout y los KPIs)
        total_items      = len(db)
        congelados_total = sum(1 for v in db.values() if v.get('estado') == 'CONGELADO')
        activos_total    = total_items - congelados_total
        racks_activos    = len(set(v.get('rack') for v in db.values() if v.get('rack')))

        # Estado de navegacion
        zona_sel = st.session_state.twin_zona
        fila_sel = st.session_state.twin_fila

        # ── NIVEL 1: Layout de nave ───────────────────────────────────────────
        if zona_sel is None:
            # Navegacion via query params
            qp = st.query_params
            if 'zona' in qp:
                st.session_state.twin_zona = qp['zona']
                st.session_state.twin_fila = qp.get('fila', None)
                st.query_params.clear()
                st.rerun()

            t5, c5 = rack_stats(db, 'POS_5')
            badge5 = '#dc3545' if c5 > 0 else '#3a3f55'  # solo rojo si hay congelados, neutro si no

            # Resaltado amarillo: activo si el rack se asignó hace menos de 5 seg
            rack_res    = st.session_state.get('rack_resaltado')
            ts_res      = st.session_state.get('rack_resaltado_ts', 0.0)
            elapsed     = time.time() - ts_res
            res_activo  = rack_res is not None and elapsed < 5

            if not res_activo and rack_res is not None:
                # Limpiar el estado una vez que pasaron los 5 seg
                st.session_state.rack_resaltado    = None
                st.session_state.rack_resaltado_ts = 0.0

            if res_activo:
                # duracion_restante para que el rerun limpie el borde justo al terminar
                duracion_restante = max(0.0, 5.0 - elapsed)
                st.markdown("""
                <style>
                @keyframes pulso_amarillo {
                    0%   { background:#2e3550; border-color:#4a5080; box-shadow:none; }
                    30%  { background:#713f12; border-color:#facc15;
                           box-shadow:0 0 18px 4px rgba(250,204,21,0.55); }
                    70%  { background:#713f12; border-color:#facc15;
                           box-shadow:0 0 18px 4px rgba(250,204,21,0.55); }
                    100% { background:#2e3550; border-color:#4a5080; box-shadow:none; }
                }
                /* animation: sin 'forwards' para que vuelva al estado inicial */
                .fila-res { animation: pulso_amarillo 5s ease !important; }
                </style>""", unsafe_allow_html=True)


            filas_html = ''
            for fila_label, rack_id in [
                ('FILA A','POS_1'),('FILA B','POS_2'),('FILA C','POS_3'),('FILA D','POS_4')
            ]:
                t, c = rack_stats(db, rack_id)
                occ = min(int(t / 60 * 100), 100)
                cb  = '#dc3545' if occ > 80 else ('#ffc107' if occ > 50 else '#28a745')
                tag = (' — LLENO' if occ >= 100 else '')
                fenc = fila_label.replace(' ', '+')
                es_res   = res_activo and rack_res == rack_id
                clase    = 'fila-res' if es_res else ''
                borde    = '#facc15' if es_res else '#4a5080'
                filas_html += (
                    f"<a href='?zona=ALMACENAJE&fila={fenc}&_s={_TOKEN_SECRETO}' target='_self' "
                    f"style='text-decoration:none;display:block;margin-bottom:8px;'>"
                    f"<div style='display:flex;align-items:center;gap:10px;'>"
                    f"<div class='{clase}' style='flex:0 0 150px;background:#2e3550;"
                    f"border:1.5px solid {borde};"
                    f"border-radius:8px;padding:11px 8px;text-align:center;color:#cdd3ea;"
                    f"font-size:12px;font-weight:600;cursor:pointer;'>{fila_label}{tag}</div>"
                    f"<div style='flex:1;'>"
                    f"<div style='font-size:10px;color:#8892b0;margin-bottom:3px;'>{t} pallets — {occ}% ocup.</div>"
                    f"<div style='background:#2a2f45;border-radius:4px;height:8px;'>"
                    f"<div style='background:{cb};width:{max(occ,1)}%;height:8px;border-radius:4px;'></div>"
                    f"</div></div></div></a>"
                )

            # Clase y borde del botón sobredimensiones
            clase_sobre = 'fila-res' if (res_activo and rack_res == 'POS_5') else ''
            borde_sobre = '#facc15'  if (res_activo and rack_res == 'POS_5') else '#4a5080'

            nave_html = (
                '<div style="display:grid;grid-template-columns:1fr 1fr 3fr 1fr;gap:8px;align-items:stretch;">'

                '<div style="background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;'
                'padding:16px 10px;text-align:center;color:#cdd3ea;'
                'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
                '<div style="font-size:10px;letter-spacing:2px;color:#8892b0;margin-bottom:10px;">RECEPCION</div>'
                '<div style="font-size:12px;color:#8892b0;">Zona de entrada</div>'
                '</div>'

                f'<div style="display:flex;flex-direction:column;gap:6px;">'
                f'<a href="?zona=SOBREDIMENSIONES&_s={_TOKEN_SECRETO}" target="_self" style="text-decoration:none;flex:1;display:flex;">'
                f'<div class="{clase_sobre}" '
                f'style="flex:1;background:#2e3550;border:1.5px solid {borde_sobre};'
                'border-radius:10px;padding:14px 10px;text-align:center;color:#cdd3ea;cursor:pointer;'
                'display:flex;flex-direction:column;align-items:center;justify-content:center;'
                'font-size:12px;font-weight:600;">'
                f'SOBREDIMENSIONES<br><span style="font-size:22px;font-weight:300;margin-top:8px;">{t5}</span>'
                '<span style="font-size:10px;color:#8892b0;margin-top:2px;">pallets</span>'
                '</div></a>'
                f'<div style="background:#2a2f45;border:1.5px solid {badge5};border-radius:8px;'
                f'padding:7px;text-align:center;color:#cdd3ea;font-size:11px;">'
                f'{t5} pallets &nbsp;&middot;&nbsp; {c5} congelados</div>'
                '</div>'

                f'<div style="background:#1e2130;border:2px dashed #3a3f55;border-radius:10px;'
                'padding:12px 14px;box-sizing:border-box;">'
                '<div style="text-align:center;color:#8892b0;font-size:10px;'
                'letter-spacing:2px;margin-bottom:12px;">ALMACENAJE</div>'
                f'{filas_html}'
                '</div>'

                '<div style="background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;'
                'padding:16px 10px;text-align:center;color:#cdd3ea;'
                'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
                '<div style="font-size:10px;letter-spacing:2px;color:#8892b0;margin-bottom:10px;">RETORNO</div>'
                '<div style="font-size:12px;color:#8892b0;">Devoluciones</div>'
                '</div>'

                '</div>'
            )
            st.markdown(nave_html, unsafe_allow_html=True)
            st.caption("Haz clic en una zona o fila para ver el detalle de posiciones.")

        # ── NIVEL 2: Sobredimensiones — vista simple sin racks ───────
        elif fila_sel is None:
            crumbs = ["Nave principal", zona_sel]
            st.markdown("  ›  ".join(f"**{c}**" for c in crumbs))
            if st.button("Volver a la nave"):
                st.session_state.twin_zona = None
                st.rerun()

            rack_id    = ZONA_A_RACK.get(zona_sel, "POS_5")
            items_zona = {k: v for k, v in db.items() if v.get('rack') == rack_id}
            st.subheader(f"Zona: {zona_sel}  |  {len(items_zona)} pallets registrados")

            if items_zona:
                filas_sobre = []
                for k, v in items_zona.items():
                    filas_sobre.append({
                        "MATRICULA": k,
                        "NOMBRE": v.get('nombre',''),
                        "SKU": v.get('sku_base','N/A'),
                        "PZAS": v.get('cantidad',1),
                        "PESO (KG)": v.get('peso',0),
                        "ESTADO": v.get('estado','ACTIVO'),
                    })
                st.dataframe(pd.DataFrame(filas_sobre), use_container_width=True)
            else:
                st.info("No hay materiales en zona de sobredimensiones.")

        # ── NIVEL 3: Fila A/B/C/D — 5 racks × 3 niveles × 3 posiciones ──
        else:
            crumbs = ["Nave principal", zona_sel, fila_sel]
            st.markdown("  ›  ".join(f"**{c}**" for c in crumbs))
            if st.button("Volver a la nave"):
                st.session_state.twin_zona = None
                st.session_state.twin_fila = None
                st.rerun()

            rack_id    = ZONA_A_RACK.get(fila_sel, "POS_1")
            st.subheader(f"{fila_sel}  |  Rack: {rack_id}")

            busq = st.text_input("Buscar material:", "").strip().upper()
            items_rack = {k: v for k, v in db.items() if v.get('rack') == rack_id}

            ICONO = (
                "<svg width='34' height='34' viewBox='0 0 100 100' "
                "xmlns='http://www.w3.org/2000/svg'>"
                "<!-- cuerpo de la caja -->"
                "<rect x='8' y='38' width='84' height='56' rx='4' fill='none' stroke='white' stroke-width='5'/>"
                "<!-- tapa izquierda -->"
                "<path d='M8 38 L8 18 L50 14' stroke='white' stroke-width='5' fill='none' stroke-linejoin='round'/>"
                "<!-- tapa derecha -->"
                "<path d='M92 38 L92 18 L50 14' stroke='white' stroke-width='5' fill='none' stroke-linejoin='round'/>"
                "<!-- linea horizontal del cuerpo -->"
                "<line x1='8' y1='60' x2='92' y2='60' stroke='white' stroke-width='4'/>"
                "<!-- asas de la tapa (hendidura) -->"
                "<rect x='34' y='22' width='32' height='10' rx='5' fill='none' stroke='white' stroke-width='4'/>"
                "<!-- simbolo flechas arriba -->"
                "<text x='72' y='88' font-size='18' fill='white' text-anchor='middle' "
                "font-family='sans-serif' font-weight='bold'>^</text>"
                "<!-- mini recuadro simbolo -->"
                "<rect x='60' y='68' width='24' height='22' rx='2' fill='none' stroke='white' stroke-width='3'/>"
                "</svg>"
            )

            st.markdown(
                "<div style='display:flex;gap:20px;margin-bottom:14px;font-size:12px;color:#cdd3ea;'>"
                "<span><span style='display:inline-block;width:12px;height:12px;"
                "background:#1a472a;border-radius:3px;margin-right:5px;'></span>Ocupado</span>"
                "<span><span style='display:inline-block;width:12px;height:12px;"
                "background:#7f1d1d;border-radius:3px;margin-right:5px;'></span>Congelado</span>"
                "<span><span style='display:inline-block;width:12px;height:12px;"
                "background:#1e2130;border:1px solid #3a3f55;border-radius:3px;margin-right:5px;'></span>"
                "Disponible</span></div>",
                unsafe_allow_html=True
            )

            # 5 racks, cada uno: 3 niveles × 3 posiciones
            NUM_RACKS   = 5
            NUM_NIVELES = 3
            NUM_COLS    = 3
            CELL_H      = 115

            racks_html = "<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:10px;'>"

            for rack_num in range(1, NUM_RACKS + 1):
                rack_html = (
                    f"<div style='background:#16192a;border:1.5px solid #3a3f55;"
                    f"border-radius:10px;padding:8px;'>"
                    f"<div style='text-align:center;font-size:10px;letter-spacing:1px;"
                    f"color:#8892b0;margin-bottom:6px;font-weight:600;'>RACK {rack_num}</div>"
                    f"<div style='display:grid;grid-template-columns:repeat({NUM_COLS},1fr);gap:3px;'>"
                )

                for nivel in range(NUM_NIVELES, 0, -1):
                    for col in range(1, NUM_COLS + 1):
                        item, item_key = None, None
                        for k, v in items_rack.items():
                            if (v.get('piso') == rack_num and
                                    v.get('fila') == nivel and
                                    v.get('columna') == col):
                                item = v; item_key = k; break

                        buscado = busq and item and (
                            busq in item.get('nombre','').upper() or
                            busq in item.get('sku_base','').upper() or
                            (item_key and busq in item_key.upper())
                        )

                        if buscado:
                            bg = "#0c3559"; border = "#3b9edd"
                        elif item:
                            congelado = item.get('estado') == 'CONGELADO'
                            bg     = "#7f1d1d" if congelado else "#1a472a"
                            border = "#ef4444" if congelado else "#22c55e"
                        else:
                            bg = "#1e2130"; border = "#3a3f55"

                        label = f"N{nivel}-P{col}"
                        if item:
                            nombre_corto = item['nombre'][:10] + ('…' if len(item['nombre']) > 10 else '')
                            tooltip = f"{item['nombre']} | SKU: {item.get('sku_base','N/A')} | {item.get('cantidad',1)} pzas"
                            contenido = (
                                f"<div title='{tooltip}' style='display:flex;flex-direction:column;"
                                f"align-items:center;justify-content:center;height:100%;gap:2px;padding:4px;'>"
                                f"{ICONO}"
                                f"<span style='font-size:7px;color:white;margin-top:2px;"
                                f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
                                f"width:95%;text-align:center;'>{nombre_corto}</span>"
                                f"<span style='font-size:6px;color:rgba(255,255,255,0.5);'>{label}</span>"
                                f"</div>"
                            )
                        else:
                            contenido = (
                                f"<div style='display:flex;align-items:center;"
                                f"justify-content:center;height:100%;'>"
                                f"<span style='font-size:7px;color:#4a5080;'>{label}</span>"
                                f"</div>"
                            )

                        rack_html += (
                            f"<div style='background:{bg};border:1px solid {border};"
                            f"border-radius:4px;height:{CELL_H}px;box-sizing:border-box;'>"
                            f"{contenido}</div>"
                        )

                rack_html += "</div></div>"
                racks_html += rack_html

            racks_html += "</div>"
            st.markdown(racks_html, unsafe_allow_html=True)

        # ── KPIs — cambian según nivel de navegacion ────────────────
        st.markdown("---")

        if zona_sel is None:
            # Vista general: KPIs globales + barra activos/congelados
            pct_activos    = round(activos_total    / total_items * 100) if total_items else 0
            pct_congelados = round(congelados_total / total_items * 100) if total_items else 0

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total pallets", total_items)
            k2.metric("Activos",       activos_total)
            k3.metric("Congelados",    congelados_total)
            k4.metric("Racks en uso",  racks_activos)

            # Barra de composicion activos / congelados
            st.markdown(
                f"<div style='margin-top:6px;'>"
                f"<div style='display:flex;justify-content:space-between;font-size:11px;"
                f"color:#8892b0;margin-bottom:4px;'>"
                f"<span>Activos {pct_activos}%</span>"
                f"<span>Congelados {pct_congelados}%</span>"
                f"</div>"
                f"<div style='display:flex;height:10px;border-radius:6px;overflow:hidden;"
                f"background:#2a2f45;'>"
                f"<div style='width:{pct_activos}%;background:#22c55e;transition:width 0.4s;'></div>"
                f"<div style='width:{pct_congelados}%;background:#ef4444;transition:width 0.4s;'></div>"
                f"</div></div>",
                unsafe_allow_html=True
            )

        else:
            # Vista de fila: KPIs específicos de esa fila
            rack_id_kpi = ZONA_A_RACK.get(fila_sel or zona_sel, "POS_1")
            items_fila_kpi = [v for v in db.values() if v.get('rack') == rack_id_kpi]

            total_fila      = len(items_fila_kpi)
            activos_fila    = sum(1 for v in items_fila_kpi if v.get('estado') == 'ACTIVO')
            congelados_fila = sum(1 for v in items_fila_kpi if v.get('estado') == 'CONGELADO')
            bajas_fila      = sum(1 for v in items_fila_kpi if v.get('estado') == 'BAJA')
            cap_total       = NUM_PISOS * NUM_NIVELES * NUM_COLS   # 5×3×3 = 45
            ocupacion_fila  = round(total_fila / cap_total * 100) if cap_total else 0
            peso_total_fila = round(sum(v.get('peso', 0) for v in items_fila_kpi), 1)

            pct_act  = round(activos_fila    / total_fila * 100) if total_fila else 0
            pct_cong = round(congelados_fila / total_fila * 100) if total_fila else 0

            fk1, fk2, fk3, fk4, fk5 = st.columns(5)
            fk1.metric("Pallets en fila",  total_fila)
            fk2.metric("Activos",          activos_fila)
            fk3.metric("Congelados",       congelados_fila)
            fk4.metric("Ocupacion",        f"{ocupacion_fila}%")
            fk5.metric("Peso total (kg)",  peso_total_fila)

            # Barra activos / congelados de la fila
            st.markdown(
                f"<div style='margin-top:6px;'>"
                f"<div style='display:flex;justify-content:space-between;font-size:11px;"
                f"color:#8892b0;margin-bottom:4px;'>"
                f"<span>Activos {pct_act}%</span>"
                f"<span>Congelados {pct_cong}%</span>"
                f"</div>"
                f"<div style='display:flex;height:10px;border-radius:6px;overflow:hidden;"
                f"background:#2a2f45;'>"
                f"<div style='width:{pct_act}%;background:#22c55e;transition:width 0.4s;'></div>"
                f"<div style='width:{pct_cong}%;background:#ef4444;transition:width 0.4s;'></div>"
                f"</div></div>",
                unsafe_allow_html=True
            )
            if bajas_fila:
                st.caption(f"{bajas_fila} pallet(s) dados de baja en esta fila.")

    with tabs[1]:
        import datetime
        st.header("GESTION DEL INVENTARIO")
        db_actual = cargar_db()

        # ── Tabla principal con filtros ───────────────────────────
        if db_actual:
            data_tabla = []
            for k, v in db_actual.items():
                data_tabla.append({
                    "MATRICULA (QR)": k,
                    "SKU":            v.get('sku_base', 'N/A'),
                    "NOMBRE":         v.get('nombre', ''),
                    "PZAS":           int(v.get('cantidad', 1)),
                    "PESO (KG)":      float(v.get('peso', 0.0)),
                    "ALTO (M)":       float(v.get('alto_m', 0.0)),
                    "RACK":           v.get('rack', ''),
                    "PISO":           v.get('piso', ''),
                    "NIVEL":          v.get('fila', ''),
                    "COL":            v.get('columna', ''),
                    "EMBALAJE":       v.get('embalaje', 'N/A'),
                    "ESTADO":         v.get('estado', 'ACTIVO'),
                    "FECHA LLEGADA":  v.get('fecha_llegada', 'N/A'),
                })
            df_full = pd.DataFrame(data_tabla)

            # Filtros — fila 1
            st.markdown("#### Filtros")
            fc1, fc2, fc3, fc4 = st.columns(4)
            with fc1:
                f_nombre = st.text_input("Nombre", "").strip().upper()
            with fc2:
                f_sku = st.text_input("Codigo / Matricula", "").strip().upper()
            with fc3:
                f_peso_max = st.number_input(
                    "Peso max (KG)", min_value=0.0,
                    value=float(df_full["PESO (KG)"].max()) if len(df_full) else 9999.0,
                    step=10.0
                )
            with fc4:
                f_estado = st.selectbox("Estado", ["TODOS", "ACTIVO", "CONGELADO", "BAJA"])

            # Filtros — fila 2 (altura)
            fa1, fa2, _ = st.columns(3)
            with fa1:
                f_alto_min = st.number_input(
                    "Alto min (M)", min_value=0.0,
                    value=0.0, step=0.1, format="%.2f"
                )
            with fa2:
                f_alto_max = st.number_input(
                    "Alto max (M)", min_value=0.0,
                    value=float(df_full["ALTO (M)"].max()) if len(df_full) else 9.99,
                    step=0.1, format="%.2f"
                )

            df_f = df_full.copy()
            if f_nombre:
                df_f = df_f[df_f["NOMBRE"].str.upper().str.contains(f_nombre, na=False)]
            if f_sku:
                df_f = df_f[
                    df_f["SKU"].str.upper().str.contains(f_sku, na=False) |
                    df_f["MATRICULA (QR)"].str.upper().str.contains(f_sku, na=False)
                ]
            df_f = df_f[df_f["PESO (KG)"] <= f_peso_max]
            df_f = df_f[(df_f["ALTO (M)"] >= f_alto_min) & (df_f["ALTO (M)"] <= f_alto_max)]
            if f_estado != "TODOS":
                df_f = df_f[df_f["ESTADO"] == f_estado]

            st.caption(f"{len(df_f)} de {len(df_full)} articulos")

            st.dataframe(
                df_f,
                use_container_width=True,
                height=max(120, min(420, 44 + len(df_f) * 36)),
                column_config={
                    "MATRICULA (QR)": st.column_config.TextColumn("Matricula QR", width="medium"),
                    "NOMBRE":         st.column_config.TextColumn("Nombre",       width="large"),
                    "SKU":            st.column_config.TextColumn("SKU",          width="small"),
                    "PZAS":           st.column_config.NumberColumn("Pzas",       width="small"),
                    "PESO (KG)":      st.column_config.NumberColumn("Peso (kg)",  width="small", format="%.1f"),
                    "ALTO (M)":       st.column_config.NumberColumn("Alto (m)",   width="small", format="%.2f"),
                    "RACK":           st.column_config.TextColumn("Rack",         width="small"),
                    "PISO":           st.column_config.TextColumn("Piso",         width="small"),
                    "NIVEL":          st.column_config.TextColumn("Nivel",        width="small"),
                    "COL":            st.column_config.TextColumn("Col",          width="small"),
                    "EMBALAJE":       st.column_config.TextColumn("Embalaje",     width="medium"),
                    "ESTADO":         st.column_config.TextColumn("Estado",       width="small"),
                    "FECHA LLEGADA":  st.column_config.TextColumn("Fecha llegada",width="medium"),
                },
                hide_index=True,
            )

            st.divider()

            # ── Seleccionar articulo para editar / dar de baja ────
            st.markdown("##### Seleccionar articulo")
            uid_sel = st.selectbox(
                "Matricula QR",
                options=["— selecciona —"] + list(db_actual.keys()),
                key="sel_matricula"
            )

            if uid_sel != "— selecciona —" and uid_sel in db_actual:
                datos = db_actual[uid_sel]
                st.markdown(f"**Editando:** {uid_sel} — {datos.get('nombre','')}")

                ed1, ed2, ed3 = st.columns(3)
                with ed1:
                    nuevo_sku    = st.text_input("SKU BASE", value=datos.get('sku_base', ''), key="e_sku")
                    nuevo_nombre = st.text_input("NOMBRE",   value=datos.get('nombre', ''),   key="e_nom")
                with ed2:
                    nueva_cant   = st.number_input("PIEZAS", min_value=1,
                                                   value=int(datos.get('cantidad', 1)), key="e_cant")
                    nuevo_peso   = st.number_input("PESO (KG)", min_value=0.0,
                                                   value=float(datos.get('peso', 0.0)), key="e_peso")
                with ed3:
                    nuevo_estado = st.selectbox("ESTADO", ["ACTIVO", "CONGELADO"],
                                                index=0 if datos.get('estado') == "ACTIVO" else 1,
                                                key="e_estado")
                    nuevo_vol    = st.number_input("VOLUMEN (M3)", min_value=0.0,
                                                   value=float(datos.get('volumen', 0.0)),
                                                   step=0.1, key="e_vol")

                rack_actual = datos.get('rack', 'POS_1')
                rack_ideal  = asignar_rack_por_peso_vol(nuevo_peso, nuevo_vol)
                if rack_actual != rack_ideal:
                    st.warning(f"ALERTA: Por peso/volumen este material deberia estar en {rack_ideal} (actualmente {rack_actual}).")

                ba1, ba2, ba3 = st.columns(3)
                with ba1:
                    if st.button("GUARDAR CAMBIOS", use_container_width=True):
                        db_actual[uid_sel].update({
                            'sku_base': nuevo_sku, 'nombre': nuevo_nombre,
                            'cantidad': nueva_cant, 'estado': nuevo_estado,
                            'peso': nuevo_peso, 'volumen': nuevo_vol
                        })
                        guardar_db(db_actual)
                        st.success("CAMBIOS GUARDADOS.")
                        st.rerun()
                with ba2:
                    if st.button("DAR DE BAJA", use_container_width=True):
                        # Marca como BAJA sin eliminar (trazabilidad)
                        db_actual[uid_sel]['estado'] = 'BAJA'
                        db_actual[uid_sel]['fecha_baja'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                        guardar_db(db_actual)
                        st.warning(f"Pallet {uid_sel} dado de baja.")
                        st.rerun()
                with ba3:
                    if st.button("ELIMINAR PERMANENTE", use_container_width=True):
                        del db_actual[uid_sel]
                        guardar_db(db_actual)
                        st.error("Pallet eliminado permanentemente.")
                        st.rerun()

        st.divider()

        # ── Alta de materiales ────────────────────────────────────
        with st.expander("ALTA DE MATERIALES Y ASIGNACION MANUAL", expanded=False):
            with st.form("new_part_manual"):

                # — Identificacion —
                st.markdown("**Identificacion**")
                c_id, c_sk, c_nm = st.columns(3)
                with c_id: new_uid      = st.text_input("ID UNICO (EJ. PALLET-010)").upper()
                with c_sk: new_sku_base = st.text_input("SKU / NUMERO DE PARTE")
                with c_nm: new_name     = st.text_input("DESCRIPCION DEL MATERIAL")

                # — Embalaje —
                st.markdown("**Tipo de embalaje**")
                emb1, emb2 = st.columns(2)
                with emb1:
                    tipo_embalaje = st.selectbox("Tipo de embalaje", TIPOS_EMBALAJE)
                with emb2:
                    embalaje_obs = st.text_input("Observaciones de embalaje (opcional)", "")

                # — Peso y cantidad —
                st.markdown("**Peso y cantidad**")
                c_p, c_c = st.columns(2)
                with c_p: p           = st.number_input("PESO TOTAL PALLET (KG)", min_value=0.0, step=1.0)
                with c_c: cant_manual = st.number_input("CANTIDAD DE PIEZAS",     min_value=1, value=1)

                # — Dimensiones (largo, ancho, alto en cm) —
                st.markdown("**Dimensiones del material**")
                st.caption(
                    "Reglas de altura: < 100 cm libre en cualquier nivel | "
                    "100–150 cm: niveles 1 y 2 | 150–180 cm: solo nivel 3 | > 180 cm: sobredimensiones"
                )
                h_cm = st.number_input("ALTO DEL MATERIAL (CM)", min_value=0.0, step=1.0,
                                       help="Determina en qué nivel del rack se almacenará")

                generar_qr_fisico = st.checkbox("GENERAR CODIGO QR FISICO", value=True)
                submitted = st.form_submit_button("REGISTRAR MATERIAL", use_container_width=True)

                if submitted:
                    if not new_uid or not new_name or not new_sku_base:
                        st.error("Completa ID, SKU y Descripcion.")
                    elif new_uid in st.session_state.db:
                        st.error(f"El ID {new_uid} ya existe en el sistema.")
                    else:
                        alto_m = h_cm / 100.0
                        vol    = 0.0  # largo y ancho definidos por tipo de embalaje
                        avisos = []

                        # Discriminante de altura → puede forzar sobredimensiones
                        forzar_sobre = alto_m > ALTO_MAX_N3
                        if forzar_sobre:
                            avisos.append(f"Alto {h_cm:.0f} cm > 180 cm → SOBREDIMENSIONES.")
                            r = "POS_5"
                        elif alto_m > ALTO_MAX_N1_N2:
                            avisos.append(f"Alto {h_cm:.0f} cm > 150 cm → solo nivel 3.")
                            r = asignar_rack_por_peso_vol(p, vol)
                        else:
                            r = asignar_rack_por_peso_vol(p, vol)

                        # Discriminante de peso
                        if p > PESO_SOBRE:
                            avisos.append(f"Peso {p:.0f} kg > {PESO_SOBRE:.0f} kg → SOBREDIMENSIONES.")
                            r = "POS_5"

                        piso, nivel, columna = obtener_coordenada_libre(
                            st.session_state.db, r, peso_nuevo=p, alto_m=alto_m
                        )

                        if piso is None and r != "POS_5":
                            r = "POS_5"
                            avisos.append("Rack asignado lleno — redirigido a SOBREDIMENSIONES.")
                            piso, nivel, columna = obtener_coordenada_libre(
                                st.session_state.db, r, peso_nuevo=p, alto_m=alto_m
                            )

                        if piso is None:
                            st.error("Sin espacio disponible en ningun rack. Reorganiza el almacen.")
                        else:
                            fecha_hoy = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                            st.session_state.db[new_uid] = {
                                "sku_base":      new_sku_base,
                                "nombre":        new_name,
                                "peso":          p,
                                "cantidad":      cant_manual,
                                "volumen":       round(vol, 4),
                                "alto_m":        round(alto_m, 2),
                                "rack":          r,
                                "piso":          piso,
                                "fila":          nivel,
                                "columna":       columna,
                                "estado":        "ACTIVO",
                                "embalaje":      tipo_embalaje,
                                "embalaje_obs":  embalaje_obs,
                                "fecha_llegada": fecha_hoy,
                            }
                            guardar_db(st.session_state.db)

                            if generar_qr_fisico:
                                qr_img = qrcode.make(new_uid)
                                nombre_archivo = f"label_{new_uid}.png"
                                qr_img.save(nombre_archivo)
                                st.session_state.qr_generado = nombre_archivo

                            if st.session_state.mqtt_client:
                                st.session_state.mqtt_client.publish(TOPIC_PUB, f"{r}_ON")
                            time.sleep(0.1)
                            st.session_state.confirmacion_pendiente = r
                            st.session_state.rack_resaltado    = r
                            st.session_state.rack_resaltado_ts = time.time()
                            # Volver al layout general para ver la animacion
                            st.session_state.twin_zona = None
                            st.session_state.twin_fila = None
                            for av in avisos:
                                st.warning(av)
                            st.success(
                                f"Pallet registrado — Rack: {r} | Piso {piso} | Nivel {nivel} | Col {columna} | "
                                f"Embalaje: {tipo_embalaje}"
                            )
                            st.rerun()

        if st.session_state.qr_generado:
            st.success("MATERIAL REGISTRADO. ESPERANDO CONFIRMACION FISICA EN EL RACK.")
            st.image(st.session_state.qr_generado, width=200, caption="CODIGO QR LISTO PARA IMPRESION")
            if st.button("LIMPIAR PANTALLA DE IMPRESION"):
                st.session_state.qr_generado = None
                st.rerun()

else:
    with tabs[0]:
        st.subheader("CAPTURA DE PALLET FISICO")

        if st.session_state.sku_pendiente is None:
            foto = st.camera_input("ESCANEA EL CODIGO QR DEL PALLET:")
            if foto:
                img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
                qrs = decode(img)
                if qrs:
                    uid_pallet = qrs[0].data.decode('utf-8').strip().upper()

                    if uid_pallet in st.session_state.db:
                        item = st.session_state.db[uid_pallet]
                        if item.get('estado') == "CONGELADO":
                            st.error(
                                f"ALERTA OPERATIVA: EL PALLET {uid_pallet} ESTA CONGELADO. NO MOVER."
                            )
                        else:
                            if uid_pallet != st.session_state.ultimo_sku_procesado:
                                st.success(
                                    f"IDENTIFICADO: {item['nombre']} "
                                    f"({item.get('cantidad', 1)} pzas) | RACK: {item['rack']}"
                                )
                                if st.session_state.mqtt_client:
                                    st.session_state.mqtt_client.publish(
                                        TOPIC_PUB, f"{item['rack']}_ON"
                                    )
                                st.session_state.confirmacion_pendiente = item['rack']
                                st.session_state.ultimo_sku_procesado   = uid_pallet
                                st.rerun()
                            else:
                                st.info(f"Visualizando pallet en {item['rack']}. Hardware activado.")
                    else:
                        st.session_state.sku_pendiente = uid_pallet
                        st.session_state.ultimo_sku_procesado = None
                        st.rerun()
            else:
                st.session_state.ultimo_sku_procesado = None

        else:
            st.warning(f"QR DE PALLET NUEVO DETECTADO: {st.session_state.sku_pendiente}")
            with st.form("reg_cloud"):
                c_sku, c_nom = st.columns(2)
                with c_sku: sku_base = st.text_input("SKU / NUMERO DE PARTE DE LA PIEZA")
                with c_nom: nom      = st.text_input("DESCRIPCION DE LA PIEZA")

                c_peso, c_cant = st.columns(2)
                with c_peso: peso = st.number_input("PESO TOTAL DEL PALLET (KG)", min_value=0.0)
                with c_cant: cant = st.number_input("CANTIDAD DE PIEZAS EN EL PALLET", min_value=1, value=1)

                c1, c2, c3 = st.columns(3)
                with c1: l = st.number_input("LARGO (CM)", min_value=0.0)
                with c2: a = st.number_input("ANCHO (CM)", min_value=0.0)
                with c3: h = st.number_input("ALTO (CM)",  min_value=0.0)

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1: submit   = st.form_submit_button("REGISTRAR PALLET Y ALMACENAR")
                with col_btn2: cancelar = st.form_submit_button("CANCELAR ESCANEO")

                if cancelar:
                    st.session_state.sku_pendiente = None
                    st.rerun()

                if submit and nom and sku_base:
                    import datetime as _dt_sc
                    alto_sc = h / 100.0
                    vol     = (l * a * h) / 1_000_000
                    avisos_sc = []

                    # Discriminante altura
                    if alto_sc > ALTO_MAX_N3:
                        avisos_sc.append(f"Alto {h:.0f} cm > 180 cm — SOBREDIMENSIONES.")
                        rack = "POS_5"
                    elif alto_sc > ALTO_MAX_N1_N2:
                        avisos_sc.append(f"Alto {h:.0f} cm > 150 cm — solo nivel 3.")
                        rack = asignar_rack_por_peso_vol(peso, vol)
                    else:
                        rack = asignar_rack_por_peso_vol(peso, vol)

                    # Discriminante peso
                    if peso > PESO_SOBRE:
                        avisos_sc.append(f"Peso {peso:.0f} kg > {PESO_SOBRE:.0f} kg — SOBREDIMENSIONES.")
                        rack = "POS_5"

                    piso, fila, col_num = obtener_coordenada_libre(
                        st.session_state.db, rack, peso_nuevo=peso, alto_m=alto_sc)

                    if piso is None and rack != "POS_5":
                        rack = "POS_5"
                        avisos_sc.append("Rack lleno — redirigido a SOBREDIMENSIONES.")
                        piso, fila, col_num = obtener_coordenada_libre(
                            st.session_state.db, rack, peso_nuevo=peso, alto_m=alto_sc)

                    if piso is not None:
                        fecha_sc = _dt_sc.datetime.now().strftime("%Y-%m-%d %H:%M")
                        st.session_state.db[st.session_state.sku_pendiente] = {
                            "sku_base": sku_base, "nombre": nom,
                            "peso": peso, "cantidad": cant,
                            "volumen": round(vol, 4),
                            "alto_m": round(alto_sc, 2),
                            "rack": rack, "piso": piso,
                            "fila": fila, "columna": col_num,
                            "estado": "ACTIVO",
                            "fecha_llegada": fecha_sc,
                        }
                        guardar_db(st.session_state.db)
                        for av in avisos_sc:
                            st.warning(av)
                        if st.session_state.mqtt_client:
                            st.session_state.mqtt_client.publish(TOPIC_PUB, f"{rack}_ON")
                        time.sleep(0.1)
                        st.session_state.confirmacion_pendiente = rack
                        st.session_state.rack_resaltado    = rack
                        st.session_state.rack_resaltado_ts = time.time()
                        st.session_state.sku_pendiente = None
                        st.success(f"PALLET REGISTRADO — Rack: {rack} | Piso {piso} | Nivel {fila} | Col {col_num}")
                        st.rerun()
                    else:
                        st.error(f"ERROR: Sin espacio disponible. Reorganiza el almacen.")

    with tabs[1]:
        import datetime as _dt
        st.subheader("ALTA RAPIDA DE MATERIAL")
        db_movil = cargar_db()
        with st.form("alta_movil"):
            uid_m = st.text_input("ID del pallet (ej. PALLET-020)").upper()
            sku_m = st.text_input("SKU / No. de parte")
            nom_m = st.text_input("Descripcion del material")
            emb_m = st.selectbox("Tipo de embalaje", TIPOS_EMBALAJE)
            col_pm, col_cm = st.columns(2)
            with col_pm: peso_m = st.number_input("Peso (KG)", min_value=0.0, step=1.0)
            with col_cm: cant_m = st.number_input("Piezas",    min_value=1,   value=1)
            alto_cm = st.number_input("Alto (CM)", min_value=0.0, step=1.0)
            gen_qr  = st.checkbox("Generar QR", value=True)
            if st.form_submit_button("REGISTRAR", use_container_width=True):
                if not uid_m or not nom_m or not sku_m:
                    st.error("Completa ID, SKU y descripcion.")
                elif uid_m in db_movil:
                    st.error(f"El ID {uid_m} ya existe.")
                else:
                    alto_v = alto_cm / 100.0
                    r_m    = asignar_rack_por_peso_vol(peso_m, 0.0)
                    if alto_v > ALTO_MAX_N3 or peso_m > PESO_SOBRE:
                        r_m = "POS_5"
                    piso_m, niv_m, col_m = obtener_coordenada_libre(
                        db_movil, r_m, peso_nuevo=peso_m, alto_m=alto_v)
                    if piso_m is None:
                        r_m = "POS_5"
                        piso_m, niv_m, col_m = obtener_coordenada_libre(
                            db_movil, r_m, peso_nuevo=peso_m, alto_m=alto_v)
                    if piso_m is None:
                        st.error("Sin espacio disponible. Reorganiza el almacen.")
                    else:
                        db_movil[uid_m] = {
                            "sku_base": sku_m, "nombre": nom_m,
                            "peso": peso_m, "cantidad": cant_m,
                            "volumen": 0.0, "alto_m": round(alto_v, 2),
                            "rack": r_m, "piso": piso_m,
                            "fila": niv_m, "columna": col_m,
                            "estado": "ACTIVO", "embalaje": emb_m,
                            "fecha_llegada": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        }
                        guardar_db(db_movil)
                        st.session_state.db = db_movil
                        if st.session_state.mqtt_client:
                            st.session_state.mqtt_client.publish(TOPIC_PUB, f"{r_m}_ON")
                        st.session_state.rack_resaltado    = r_m
                        st.session_state.rack_resaltado_ts = time.time()
                        st.session_state.confirmacion_pendiente = r_m
                        if gen_qr:
                            qr_img = qrcode.make(uid_m)
                            qr_img.save(f"label_{uid_m}.png")
                            st.session_state.qr_generado = f"label_{uid_m}.png"
                        st.success(
                            f"Registrado en {r_m} — Piso {piso_m}, Nivel {niv_m}, Col {col_m}")
                        st.rerun()
        if st.session_state.qr_generado:
            st.image(st.session_state.qr_generado, width=220, caption="QR listo")
            if st.button("Limpiar QR"):
                st.session_state.qr_generado = None
                st.rerun()
