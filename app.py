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
FIREBASE_URL     = get_secret("FIREBASE_URL", "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json")
HISTORIAL_URL    = FIREBASE_URL.replace("maestro_articulos.json", "historial.json")

def cargar_db(forzar=False):
    """
    Lee la DB de Firebase solo si:
    - Es la primera carga (session_state.db es None)
    - Se pide explicitamente con forzar=True
    En cualquier otro caso devuelve el cache de session_state.
    """
    if not forzar and st.session_state.get('db') is not None:
        return st.session_state.db
    try:
        res = requests.get(FIREBASE_URL, timeout=5)
        if res.status_code == 200 and res.json() is not None:
            st.session_state.db = res.json()
            return st.session_state.db
    except Exception as e:
        st.error(f"ERROR DE CONEXION CON FIREBASE: {e}")
    return st.session_state.get('db') or {}

def guardar_db(db):
    try:
        requests.put(FIREBASE_URL, json=db, timeout=5)
        st.session_state.db = db
    except Exception as e:
        st.error(f"ERROR AL GUARDAR EN FIREBASE: {e}")

def registrar_movimiento(accion, uid, detalle='', rol=None):
    """Guarda un evento en /historial de Firebase. No bloquea si falla."""
    import datetime as _dt
    try:
        res = requests.get(HISTORIAL_URL, timeout=5)
        historial = res.json() if res.status_code == 200 and res.json() else {}
        ts  = _dt.datetime.now()
        key = ts.strftime('%Y%m%d_%H%M%S_') + uid[:8].replace('-','_')
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

# ─────────────────────────────────────────
# CONFIGURACION MQTT
# ─────────────────────────────────────────
MQTT_HOST  = get_secret("MQTT_HOST",  "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud")
MQTT_PORT  = int(get_secret("MQTT_PORT", "8883"))
MQTT_USER  = get_secret("MQTT_USER",  "logistica123")
MQTT_PASS  = get_secret("MQTT_PASS",  "Logistica1")
TOPIC_PUB  = "almacen/escaneo"
TOPIC_SUB  = "almacen/confirmacion"
TOPIC_AUTH = "almacen/rfid"

# ─── Seguridad ───────────────────────────────────────────
# UIDs autorizados: agrega aqui los de tus tarjetas/llaveros
# Para conocer el UID de una tarjeta nueva, activa modo debug en el .ino
# UIDs desde .env separados por coma: UID1,UID2
_uids_raw = get_secret("UIDS_AUTORIZADOS", "06:7F:04:07,92:D1:10:06")
UIDS_AUTORIZADOS = set(u.strip().upper() for u in _uids_raw.split(",") if u.strip())
PASSWORD_ACCESO  = get_secret("PASSWORD_ACCESO", "1234567890")  # Operador
PASSWORD_ADMIN   = get_secret("PASSWORD_ADMIN",  "1020304050")  # Administrador

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
# FUNCION UNIFICADA DE REGISTRO
# ─────────────────────────────────────────
def registrar_pallet(uid, sku_base, nombre, peso, cantidad,
                     alto_cm=0.0, embalaje="", embalaje_obs="",
                     generar_qr=False):
    """
    Registra un pallet en Firebase aplicando todos los discriminantes.
    Retorna (exito:bool, mensaje:str, avisos:list)
    """
    import datetime as _dt

    if not uid or not nombre or not sku_base:
        return False, "Completa ID, SKU y descripcion.", []

    db = st.session_state.db or {}
    if uid in db:
        return False, f"El ID {uid} ya existe en el sistema.", []

    alto_m  = alto_cm / 100.0
    avisos  = []

    # Discriminante de altura
    if alto_m > ALTO_MAX_N3:
        avisos.append(f"Alto {alto_cm:.0f} cm > 180 cm — asignado a SOBREDIMENSIONES.")
        r = "POS_5"
    elif alto_m > ALTO_MAX_N1_N2:
        avisos.append(f"Alto {alto_cm:.0f} cm > 150 cm — solo nivel 3.")
        r = asignar_rack_por_peso_vol(peso, 0.0)
    else:
        r = asignar_rack_por_peso_vol(peso, 0.0)

    # Discriminante de peso
    if peso > PESO_SOBRE:
        avisos.append(f"Peso {peso:.0f} kg > {PESO_SOBRE:.0f} kg — asignado a SOBREDIMENSIONES.")
        r = "POS_5"

    # Buscar coordenada libre
    piso, nivel, col = obtener_coordenada_libre(db, r, peso_nuevo=peso, alto_m=alto_m)

    # Fallback a sobredimensiones si el rack está lleno
    if piso is None and r != "POS_5":
        r = "POS_5"
        avisos.append("Rack asignado lleno — redirigido a SOBREDIMENSIONES.")
        piso, nivel, col = obtener_coordenada_libre(db, r, peso_nuevo=peso, alto_m=alto_m)

    if piso is None:
        return False, "Sin espacio disponible en ningun rack. Reorganiza el almacen.", avisos

    # Guardar en Firebase
    fecha = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    registro = {
        "sku_base":      sku_base,
        "nombre":        nombre,
        "peso":          peso,
        "cantidad":      cantidad,
        "volumen":       0.0,
        "alto_m":        round(alto_m, 2),
        "rack":          r,
        "piso":          piso,
        "fila":          nivel,
        "columna":       col,
        "estado":        "ACTIVO",
        "embalaje":      embalaje,
        "embalaje_obs":  embalaje_obs,
        "fecha_llegada": fecha,
    }
    st.session_state.db[uid] = registro
    guardar_db(st.session_state.db)
    registrar_movimiento('ALTA', uid,
        f"{nombre} | SKU: {sku_base} | Rack: {r} | Piso {piso} Niv {nivel} Col {col} | {peso}kg")

    # Generar QR si se solicita
    if generar_qr:
        qr_img = qrcode.make(uid)
        nombre_archivo = f"label_{uid}.png"
        qr_img.save(nombre_archivo)
        st.session_state.qr_generado = nombre_archivo

    # Activar LED del rack
    if st.session_state.get('mqtt_client'):
        st.session_state.mqtt_client.publish(TOPIC_PUB, f"{r}_ON")
    time.sleep(0.1)

    # Actualizar estado de resaltado y navegacion
    st.session_state.confirmacion_pendiente = r
    st.session_state.rack_resaltado         = r
    st.session_state.rack_resaltado_ts      = time.time()
    st.session_state.twin_zona              = None
    st.session_state.twin_fila              = None

    msg = f"Pallet registrado — Rack: {r} | Piso {piso} | Nivel {nivel} | Col {col}"
    return True, msg, avisos

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
    'twin_rack': None,
    'rack_resaltado': None,
    'rack_resaltado_ts': 0.0,
    'es_movil': None,           # None = aun no detectado
    # Autenticacion
    'autenticado': False,
    'rol': 'operador',          # 'admin' o 'operador'
    'uid_rfid_recibido': None,
    'intentos_password': 0,
    'bloqueado_hasta': 0.0,
    'session_token': None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.db is None:
    cargar_db(forzar=True)  # carga inicial desde Firebase

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
            st.session_state.rol               = 'admin'
            st.session_state.intentos_password = 0
            st.session_state.session_token     = _TOKEN_SECRETO + '_admin'
            st.query_params['_s'] = _TOK_ACTIVO + '_admin'
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
                if pwd == PASSWORD_ADMIN:
                    st.session_state.autenticado       = True
                    st.session_state.rol               = 'admin'
                    st.session_state.intentos_password = 0
                    st.session_state.session_token     = _TOKEN_ADMIN_PWD + '_admin'
                    st.query_params['_s'] = _TOKEN_ADMIN_PWD + '_admin'
                    st.rerun()
                elif pwd == PASSWORD_ACCESO:
                    st.session_state.autenticado       = True
                    st.session_state.rol               = 'operador'
                    st.session_state.intentos_password = 0
                    st.session_state.session_token     = _TOKEN_SECRETO + '_operador'
                    st.query_params['_s'] = _TOK_ACTIVO + '_operador'
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
_TOKEN_SECRETO       = _hashlib.sha256(PASSWORD_ACCESO.encode()).hexdigest()[:16]
_TOKEN_ADMIN_PWD     = _hashlib.sha256(PASSWORD_ADMIN.encode()).hexdigest()[:16]

# Si el session_state se reseteo (reload por query param),
# restaurar la sesion verificando el token en la URL
if not st.session_state.get('autenticado'):
    _token_url = st.query_params.get('_s', '')
    if _token_url in (_TOKEN_SECRETO + '_admin', _TOKEN_ADMIN_PWD + '_admin'):
        st.session_state.autenticado   = True
        st.session_state.rol           = 'admin'
        st.session_state.session_token = _token_url
    elif _token_url == _TOKEN_SECRETO + '_operador':
        st.session_state.autenticado   = True
        st.session_state.rol           = 'operador'
        st.session_state.session_token = _TOKEN_SECRETO + '_operador'

if not st.session_state.get('autenticado', False):
    pantalla_login()
    st.stop()

# Token activo del usuario actual (incluye sufijo de rol)
_TOK_ACTIVO = st.session_state.get('session_token') or (_TOKEN_SECRETO + '_operador')

# Botón de cerrar sesión (esquina superior derecha)
with st.sidebar:
    st.markdown("### UMAD WMS")
    _rol_actual = st.session_state.get('rol', 'operador')
    _rol_color  = '#22c55e' if _rol_actual == 'admin' else '#8892b0'
    _rol_label  = 'Administrador' if _rol_actual == 'admin' else 'Operador'
    st.markdown(
        f"<div style='font-size:11px;color:{_rol_color};margin-bottom:4px;'"
        f">Rol: <b>{_rol_label}</b></div>",
        unsafe_allow_html=True
    )
    st.markdown("---")
    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.autenticado   = False
        st.session_state.rol           = 'operador'
        st.session_state.session_token = None
        st.query_params.clear()
        st.rerun()

# CSS global
st.markdown("""
<style>
/* Elimina el gap horizontal entre columnas en las grillas de racks */
div[data-testid="column"] > div {
    padding: 0 !important;
}
.rack-row > div[data-testid="stHorizontalBlock"] {
    gap: 6px !important;
}
.rack-row {
    margin-bottom: 6px !important;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
    padding: 0 !important;
}
/* Selectbox: solo cursor de puntero, sin seleccion de texto ni caret */
div[data-testid="stSelectbox"] input,
div[data-testid="stSelectbox"] input:hover,
div[data-testid="stSelectbox"] input:focus,
div[data-testid="stSelectbox"] input:active {
    cursor: pointer !important;
    caret-color: transparent !important;
    user-select: none !important;
    -webkit-user-select: none !important;
    -moz-user-select: none !important;
    color: transparent !important;
    text-shadow: 0 0 0 var(--text-color, #fff) !important;
}
div[data-testid="stSelectbox"] [data-baseweb="select"],
div[data-testid="stSelectbox"] [data-baseweb="select"] * {
    cursor: pointer !important;
}

</style>
""", unsafe_allow_html=True)

st.markdown(
    "<h1 style='text-align:center;color:#FF4B4B;margin-bottom:4px;'>"
    "UMAD Warehouse Management System</h1>",
    unsafe_allow_html=True
)


# ── Alertas de reorden ─────────────────────────────────
_db_alertas = st.session_state.get('db') or {}
_alertas = [
    (k, v) for k, v in _db_alertas.items()
    if int(v.get('stock_minimo', 0)) > 0
    and int(v.get('cantidad', 1)) <= int(v.get('stock_minimo', 0))
    and v.get('estado') == 'ACTIVO'
]
if _alertas:
    with st.expander(f"ALERTA DE REORDEN — {len(_alertas)} artículo(s) bajo minimo",
                     expanded=True):
        for _k, _v in _alertas:
            st.warning(
                f"{_v.get('nombre','N/A')} | SKU: {_v.get('sku_base','N/A')} | "
                f"Stock actual: {_v.get('cantidad',1)} pzas | "
                f"Minimo: {_v.get('stock_minimo',0)} pzas | "
                f"Rack: {_v.get('rack','')} Piso {_v.get('piso','')} "
                f"Niv {_v.get('fila','')} Col {_v.get('columna','')}"
            )

# ── Alertas en sidebar ───────────────────────────────────
if _alertas:
    with st.sidebar:
        st.markdown(
            f"<div style='background:#7f1d1d;border-radius:8px;padding:8px 12px;"
            f"margin-bottom:8px;font-size:12px;color:#fca5a5;'>"
            f"<b>Reorden:</b> {len(_alertas)} artículo(s)</div>",
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
        db = cargar_db(forzar=True)  # refrescar desde Firebase en cada tick

        # Calculos (necesarios para el layout y los KPIs)
        total_items      = len(db)
        congelados_total = sum(1 for v in db.values() if v.get('estado') == 'CONGELADO')
        activos_total    = total_items - congelados_total
        racks_activos    = len(set(v.get('rack') for v in db.values() if v.get('rack')))

        # Estado de navegacion
        zona_sel = st.session_state.twin_zona
        fila_sel = st.session_state.twin_fila
        rack_sel = st.session_state.get('twin_rack', None)

        # ── NIVEL 1: Layout de nave ───────────────────────────────────────────
        if zona_sel is None:
            # Navegacion via query params
            qp = st.query_params
            if 'zona' in qp:
                st.session_state.twin_zona = qp['zona']
                fila_raw = qp.get('fila', None)
                st.session_state.twin_fila = fila_raw.replace('+', ' ') if fila_raw else None
                # Si viene rack en la URL, guardarlo también
                if 'rack' in qp:
                    st.session_state.twin_rack = int(qp['rack'])
                st.query_params.clear()
                st.query_params['_s'] = _TOK_ACTIVO
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
                    f"<a href='?zona=ALMACENAJE&fila={fenc}&_s={_TOK_ACTIVO}' target='_self' "
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
                f'<a href="?zona=SOBREDIMENSIONES&_s={_TOK_ACTIVO}" target="_self" style="text-decoration:none;flex:1;display:flex;">'
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

        # ── NIVEL 3: Vista de 5 racks (resumen) ────────────────────
        elif rack_sel is None:
            crumbs = ["Nave principal", zona_sel, fila_sel]
            st.markdown("  ›  ".join(f"**{c}**" for c in crumbs))
            if st.button("Volver a la nave"):
                st.session_state.twin_zona = None
                st.session_state.twin_fila = None
                st.session_state.twin_rack = None
                st.rerun()

            rack_id    = ZONA_A_RACK.get(fila_sel, "POS_1")
            items_rack = {k: v for k, v in db.items() if v.get('rack') == rack_id}

            st.markdown(
                "<div style='display:flex;gap:20px;margin-bottom:14px;font-size:12px;color:#cdd3ea;'>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#1a472a;border-radius:2px;margin-right:4px;'></span>Ocupado</span>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#7f1d1d;border-radius:2px;margin-right:4px;'></span>Congelado</span>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#1e2130;border:1px solid #3a3f55;border-radius:2px;margin-right:4px;'></span>"
                "Disponible</span>"
                "<span style='color:#8892b0;'>— Haz clic en un rack para ver el detalle</span>"
                "</div>",
                unsafe_allow_html=True
            )

            NUM_RACKS   = 5
            NUM_NIVELES = 3
            NUM_COLS    = 3
            TOTAL_CELDAS = NUM_NIVELES * NUM_COLS  # 9 por rack

            # SVG de rack como estructura
            def svg_rack_resumen(rack_num, items_rack_local, rack_id_local):
                ocupadas = {}
                for k, v in items_rack_local.items():
                    if v.get('piso') == rack_num:
                        key = (v.get('fila'), v.get('columna'))
                        ocupadas[key] = v

                total_occ = len(ocupadas)
                occ_pct   = round(total_occ / TOTAL_CELDAS * 100)

                W, H    = 162, 172
                col_w   = 5
                pad_l   = 20
                pad_r   = 14
                pad_top = 38
                area_w  = W - pad_l - pad_r
                est_h   = (H - pad_top - 14) // NUM_NIVELES
                cel_w   = area_w // NUM_COLS

                def caja_carton(x, y, cw, ch, sc):
                    """Caja de carton entreabierta con agarradera frontal, centrada en celda."""
                    # Escalar a ~70% de la celda
                    bw = int(cw * 0.70)
                    bh = int(ch * 0.65)
                    th = int(bh * 0.28)   # alto tapa
                    # Centrar en celda
                    bx = x + (cw - bw) // 2
                    by = y + (ch - bh) // 2 + th // 2
                    mx = bx + bw // 2     # centro horizontal
                    ty = by - th          # top de tapa

                    # Agarradera (ovalo frontal centrado)
                    hx = mx - bw // 6
                    hw = bw // 3
                    hh = int(bh * 0.18)
                    hy = by + int(bh * 0.30)

                    return (
                        # Cuerpo
                        f"<rect x='{bx}' y='{by}' width='{bw}' height='{bh}' "
                        f"rx='1' fill='none' stroke='{sc}' stroke-width='1.3'/>"
                        # Tapa izquierda (entreabierta)
                        f"<line x1='{bx}' y1='{by}' x2='{bx + bw//4}' y2='{ty}' "
                        f"stroke='{sc}' stroke-width='1.2'/>"
                        # Tapa derecha (entreabierta)
                        f"<line x1='{bx+bw}' y1='{by}' x2='{bx + bw - bw//4}' y2='{ty}' "
                        f"stroke='{sc}' stroke-width='1.2'/>"
                        # Linea horizontal del cuerpo
                        f"<line x1='{bx}' y1='{by + bh//3}' x2='{bx+bw}' y2='{by + bh//3}' "
                        f"stroke='{sc}' stroke-width='0.8' opacity='0.5'/>"
                        # Agarradera frontal (rect redondeado)
                        f"<rect x='{hx}' y='{hy}' width='{hw}' height='{hh}' "
                        f"rx='{hh//2}' fill='none' stroke='{sc}' stroke-width='1.0'/>"
                    )

                svg = (
                    f"<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}' "
                    f"xmlns='http://www.w3.org/2000/svg' style='display:block;'>"
                    # Columnas estructurales
                    f"<rect x='{pad_l-col_w-2}' y='{pad_top-2}' width='{col_w}' height='{H-pad_top-8}' fill='#3a3f55'/>"
                    f"<rect x='{pad_l+area_w+2}' y='{pad_top-2}' width='{col_w}' height='{H-pad_top-8}' fill='#3a3f55'/>"
                    # Piso
                    f"<rect x='{pad_l-col_w-2}' y='{H-12}' width='{area_w+col_w*2+4}' height='5' fill='#3a3f55' rx='1'/>"
                    # Labels
                    f"<text x='{W//2}' y='16' text-anchor='middle' font-size='10' "
                    f"font-weight='600' fill='#cdd3ea' font-family='sans-serif'>RACK {rack_num}</text>"
                    f"<text x='{W//2}' y='28' text-anchor='middle' font-size='7' "
                    f"fill='#8892b0' font-family='sans-serif'>{total_occ}/{TOTAL_CELDAS} · {occ_pct}%</text>"
                )

                for ni, nivel in enumerate(range(NUM_NIVELES, 0, -1)):
                    y_base = pad_top + ni * est_h
                    # Estante
                    svg += (
                        f"<line x1='{pad_l-col_w-2}' y1='{y_base + est_h - 3}' "
                        f"x2='{pad_l+area_w+col_w+2}' y2='{y_base + est_h - 3}' "
                        f"stroke='#3a3f55' stroke-width='2.5'/>"
                    )
                    for ci, col in enumerate(range(1, NUM_COLS + 1)):
                        cx = pad_l + ci * cel_w
                        cy = y_base + 2
                        cw = cel_w - 2
                        ch = est_h - 8
                        pos = (nivel, col)

                        if pos in ocupadas:
                            item_v = ocupadas[pos]
                            cong   = item_v.get('estado') == 'CONGELADO'
                            bg     = '#1a2a1a' if not cong else '#2a1010'
                            bord   = '#22c55e' if not cong else '#ef4444'
                            sc     = '#4ade80' if not cong else '#f87171'
                        else:
                            bg = '#16192a'; bord = '#2a2f45'; sc = None

                        svg += (
                            f"<rect x='{cx}' y='{cy}' width='{cw}' height='{ch}' "
                            f"rx='2' fill='{bg}' stroke='{bord}' stroke-width='0.8'/>"
                        )
                        if sc:
                            svg += caja_carton(cx, cy, cw, ch, sc)

                svg += "</svg>"
                return svg, total_occ, occ_pct

            # Renderizar los 5 racks — el SVG completo es el enlace
            racks_grid = "<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:10px;'>"
            for rack_num in range(1, NUM_RACKS + 1):
                svg_r, occ_n, occ_p = svg_rack_resumen(rack_num, items_rack, rack_id)
                fila_enc = fila_sel.replace(' ', '+')
                url = f"?zona=ALMACENAJE&fila={fila_enc}&rack={rack_num}&_s={_TOK_ACTIVO}"
                racks_grid += (
                    f"<a href='{url}' target='_self' style='text-decoration:none;cursor:pointer;'>"
                    f"<div style='background:#16192a;border:1.5px solid #3a3f55;"
                    f"border-radius:10px;padding:8px 4px;text-align:center;"
                    f"transition:border-color 0.15s;'"
                    f"onmouseover=\"this.style.borderColor='#7f8ac0'\""
                    f"onmouseout=\"this.style.borderColor='#3a3f55'\">"
                    f"{svg_r}</div></a>"
                )
            racks_grid += "</div>"
            st.markdown(racks_grid, unsafe_allow_html=True)

            # Leer seleccion de rack via query param
            _qp_now = dict(st.query_params)
            if 'rack' in _qp_now:
                st.session_state.twin_rack = int(_qp_now['rack'])
                # Preservar zona y fila en session_state antes de limpiar
                if 'zona' in _qp_now:
                    st.session_state.twin_zona = _qp_now['zona']
                if 'fila' in _qp_now:
                    st.session_state.twin_fila = _qp_now['fila'].replace('+', ' ')
                st.query_params.clear()
                st.query_params['_s'] = _TOK_ACTIVO
                st.rerun()

        # ── NIVEL 4: Rack seleccionado en detalle ────────────────────
        else:
            rack_id    = ZONA_A_RACK.get(fila_sel, "POS_1")
            items_rack = {k: v for k, v in db.items() if v.get('rack') == rack_id}

            crumbs = ["Nave principal", zona_sel, fila_sel, f"Rack {rack_sel}"]
            st.markdown("  ›  ".join(f"**{c}**" for c in crumbs))

            cb1, cb2 = st.columns(2)
            with cb1:
                if st.button("Volver a los racks"):
                    st.session_state.twin_rack = None
                    st.rerun()
            with cb2:
                busq = st.text_input("Buscar en este rack:", "").strip().upper()

            st.markdown(
                "<div style='display:flex;gap:20px;margin-bottom:12px;font-size:12px;color:#cdd3ea;'>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#1a472a;border-radius:2px;margin-right:4px;'></span>Ocupado</span>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#7f1d1d;border-radius:2px;margin-right:4px;'></span>Congelado</span>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#0c3559;border:1px solid #3b9edd;border-radius:2px;margin-right:4px;'></span>"
                "Buscado</span>"
                "<span><span style='display:inline-block;width:10px;height:10px;"
                "background:#1e2130;border:1px solid #3a3f55;border-radius:2px;margin-right:4px;'></span>"
                "Disponible</span></div>",
                unsafe_allow_html=True
            )

            # SVG del rack — proporciones reales de rack fisico (alto > ancho)
            NUM_NIVELES = 3
            NUM_COLS    = 3
            W, H        = 340, 320
            col_w_d     = 10
            pad_l       = 32
            pad_r       = 12
            pad_top     = 38
            est_h       = (H - pad_top - 14) // NUM_NIVELES
            area_w      = W - pad_l - pad_r
            cel_w       = area_w // NUM_COLS

            svg = (
                f"<svg width='100%' viewBox='0 0 {W} {H}' "
                f"xmlns='http://www.w3.org/2000/svg' "
                f"style='display:block;max-width:340px;margin:0 auto;'>"
                # Titulo
                f"<text x='{W//2}' y='24' text-anchor='middle' font-size='16' "
                f"font-weight='600' fill='#cdd3ea' font-family='sans-serif'>"
                f"RACK {rack_sel} — {fila_sel}</text>"
                # Columnas estructurales
                f"<rect x='{pad_l-col_w_d-2}' y='{pad_top}' width='{col_w_d}' height='{H-pad_top-8}' fill='#3a3f55' rx='2'/>"
                f"<rect x='{pad_l+area_w+2}' y='{pad_top}' width='{col_w_d}' height='{H-pad_top-8}' fill='#3a3f55' rx='2'/>"
                # Piso
                f"<rect x='{pad_l-col_w_d-2}' y='{H-12}' width='{area_w+col_w_d*2+4}' height='6' fill='#3a3f55' rx='3'/>"
            )

            for ni, nivel in enumerate(range(NUM_NIVELES, 0, -1)):
                y_base = pad_top + ni * est_h
                # Etiqueta del nivel
                svg += (
                    f"<text x='{pad_l-14}' y='{y_base + est_h//2 + 4}' "
                    f"text-anchor='end' font-size='9' fill='#8892b0' font-family='sans-serif'>"
                    f"N{nivel}</text>"
                )
                # Linea del estante
                svg += (
                    f"<line x1='{pad_l-col_w_d-2}' y1='{y_base + est_h - 3}' "
                    f"x2='{pad_l+area_w+col_w_d+2}' y2='{y_base + est_h - 3}' "
                    f"stroke='#3a3f55' stroke-width='4'/>"
                )
                for ci, col in enumerate(range(1, NUM_COLS + 1)):
                    x   = pad_l + ci * cel_w + 3
                    y   = y_base + 5
                    cw  = cel_w - 6
                    ch  = est_h - 14

                    item, item_key = None, None
                    for k, v in items_rack.items():
                        if (v.get('piso') == rack_sel and
                                v.get('fila') == nivel and
                                v.get('columna') == col):
                            item = v; item_key = k; break

                    buscado = busq and item and (
                        busq in item.get('nombre','').upper() or
                        busq in item.get('sku_base','N/A').upper() or
                        (item_key and busq in item_key.upper())
                    )

                    if buscado:
                        color = '#0c3559'; bord = '#3b9edd'
                    elif item:
                        cong  = item.get('estado') == 'CONGELADO'
                        color = '#7f1d1d' if cong else '#1a472a'
                        bord  = '#ef4444' if cong else '#22c55e'
                    else:
                        color = '#16192a'; bord = '#2a2f45'

                    svg += (
                        f"<rect x='{x}' y='{y}' width='{cw}' height='{ch}' "
                        f"rx='4' fill='{color}' stroke='{bord}' stroke-width='1.5'/>"
                    )

                    # Etiqueta de posición
                    svg += (
                        f"<text x='{x + cw//2}' y='{y_base + 16}' text-anchor='middle' "
                        f"font-size='8' fill='#8892b0' font-family='sans-serif'>P{col}</text>"
                    )

                    if item:
                        nom = item.get('nombre','')
                        sku = item.get('sku_base','N/A')
                        pzs = item.get('cantidad', 1)
                        # Nombre (truncado)
                        nom_c = (nom[:14] + '…') if len(nom) > 14 else nom
                        svg += (
                            f"<text x='{x + cw//2}' y='{y + ch//2 - 14}' text-anchor='middle' "
                            f"font-size='11' font-weight='600' fill='white' font-family='sans-serif'>"
                            f"{nom_c}</text>"
                            f"<text x='{x + cw//2}' y='{y + ch//2}' text-anchor='middle' "
                            f"font-size='9' fill='rgba(255,255,255,0.7)' font-family='sans-serif'>"
                            f"{sku}</text>"
                            f"<text x='{x + cw//2}' y='{y + ch//2 + 13}' text-anchor='middle' "
                            f"font-size='9' fill='rgba(255,255,255,0.6)' font-family='sans-serif'>"
                            f"{pzs} pzas</text>"
                        )
                    else:
                        svg += (
                            f"<text x='{x + cw//2}' y='{y + ch//2 + 4}' text-anchor='middle' "
                            f"font-size='10' fill='#4a5080' font-family='sans-serif'>LIBRE</text>"
                        )

            svg += "</svg>"
            st.markdown(
                f"<div style='background:#16192a;border:1.5px solid #3a3f55;"
                f"border-radius:12px;padding:16px;'>{svg}</div>",
                unsafe_allow_html=True
            )

            # Tabla de contenido del rack
            items_este_rack = {k: v for k, v in items_rack.items()
                               if v.get('piso') == rack_sel}
            if items_este_rack:
                st.markdown(f"**{len(items_este_rack)} artículos en este rack:**")
                filas_det = []
                for k, v in items_este_rack.items():
                    filas_det.append({
                        "Matricula": k,
                        "Nombre":    v.get('nombre',''),
                        "SKU":       v.get('sku_base','N/A'),
                        "Nivel":     v.get('fila',''),
                        "Posicion":  v.get('columna',''),
                        "Pzas":      v.get('cantidad',1),
                        "Peso(kg)":  v.get('peso',0),
                        "Estado":    v.get('estado','ACTIVO'),
                    })
                st.dataframe(pd.DataFrame(filas_det), use_container_width=True,
                             hide_index=True,
                             height=44 + len(filas_det) * 36)
            else:
                st.info("Este rack está vacío.")

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
        _es_admin_m = st.session_state.get('rol') == 'admin'
        _subtabs = (["Inventario", "Historial"] if _es_admin_m else ["Inventario"])
        _st = st.tabs(_subtabs)

        with _st[0]:  # Inventario
         db_actual = cargar_db()  # usa cache

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
                    "STOCK MIN":      int(v.get('stock_minimo', 0)),
                })
            df_full = pd.DataFrame(data_tabla)

            # Busqueda rapida + filtro de estado
            fb1, fb2 = st.columns([3, 1])
            with fb1:
                f_busq = st.text_input("Buscar", "", placeholder="Nombre, SKU o Matricula...").strip().upper()
            with fb2:
                f_estado = st.selectbox(
                    "Estado",
                    options=["TODOS", "ACTIVO", "CONGELADO", "BAJA"],
                    index=0,
                    key="filtro_estado"
                )
            # Sobrescribir valor si alguien escribio algo invalido
            if f_estado not in ["TODOS", "ACTIVO", "CONGELADO", "BAJA"]:
                f_estado = "TODOS" 

            df_f = df_full.copy()
            if f_busq:
                df_f = df_f[
                    df_f["NOMBRE"].str.upper().str.contains(f_busq, na=False) |
                    df_f["SKU"].str.upper().str.contains(f_busq, na=False) |
                    df_f["MATRICULA (QR)"].str.upper().str.contains(f_busq, na=False)
                ]
            if f_estado != "TODOS":
                df_f = df_f[df_f["ESTADO"] == f_estado]

            st.caption(f"{len(df_f)} de {len(df_full)} articulos")

            st.dataframe(
                df_f,
                use_container_width=True,
                height=44 + len(df_f) * 36,
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
                datos    = db_actual[uid_sel]
                es_admin = st.session_state.get('rol') == 'admin'

                st.markdown(f"**{uid_sel}** — {datos.get('nombre','')}")

                if es_admin:
                    # Admin: formulario completo de edicion
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
                        nuevo_stock_min = st.number_input("STOCK MINIMO (pzas)", min_value=0,
                                                          value=int(datos.get('stock_minimo', 0)),
                                                          key="e_smin",
                                                          help="Alerta cuando la cantidad baje de este valor. 0 = sin alerta.")

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
                                'peso': nuevo_peso, 'volumen': nuevo_vol,
                                'stock_minimo': nuevo_stock_min
                            })
                            guardar_db(db_actual)
                            registrar_movimiento('EDICION', uid_sel,
                                f"SKU: {nuevo_sku} | Estado: {nuevo_estado} | Peso: {nuevo_peso}kg")
                            st.success("Cambios guardados.")
                            st.rerun()
                    with ba2:
                        if st.button("DAR DE BAJA", use_container_width=True):
                            db_actual[uid_sel]['estado'] = 'BAJA'
                            db_actual[uid_sel]['fecha_baja'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                            guardar_db(db_actual)
                            registrar_movimiento('BAJA', uid_sel,
                                f"{db_actual[uid_sel].get('nombre','')} | {db_actual[uid_sel].get('rack','')}")
                            st.warning(f"Pallet {uid_sel} dado de baja.")
                            st.rerun()
                    with ba3:
                        if st.button("ELIMINAR PERMANENTE", use_container_width=True):
                            _nom_eli  = db_actual[uid_sel].get('nombre','')
                            _rack_eli = db_actual[uid_sel].get('rack','')
                            registrar_movimiento('ELIMINACION', uid_sel,
                                f"{_nom_eli} | {_rack_eli}")
                            del db_actual[uid_sel]
                            guardar_db(db_actual)
                            st.error("Pallet eliminado permanentemente.")
                            st.rerun()
                else:
                    # Operador: solo consulta, sin edicion
                    st.markdown(
                        "<div style='background:#1e2130;border:1px solid #3a3f55;border-radius:8px;"
                        "padding:12px 16px;margin-top:8px;'>"
                        "<table style='width:100%;font-size:13px;color:#cdd3ea;border-collapse:collapse;'>"
                        f"<tr><td style='padding:4px 8px;color:#8892b0;'>SKU</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('sku_base','N/A')}</td>"
                        f"<td style='padding:4px 8px;color:#8892b0;'>Rack</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('rack','')} · Piso {datos.get('piso','')} · Niv {datos.get('fila','')} · Col {datos.get('columna','')}</td></tr>"
                        f"<tr><td style='padding:4px 8px;color:#8892b0;'>Peso</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('peso',0)} kg</td>"
                        f"<td style='padding:4px 8px;color:#8892b0;'>Piezas</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('cantidad',1)}</td></tr>"
                        f"<tr><td style='padding:4px 8px;color:#8892b0;'>Estado</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('estado','ACTIVO')}</td>"
                        f"<td style='padding:4px 8px;color:#8892b0;'>Embalaje</td>"
                        f"<td style='padding:4px 8px;'>{datos.get('embalaje','N/A')}</td></tr>"
                        "</table></div>",
                        unsafe_allow_html=True
                    )
                    st.info("Solo el administrador puede editar, dar de baja o eliminar materiales.")

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
                    ok, msg, avisos = registrar_pallet(
                        uid=new_uid, sku_base=new_sku_base, nombre=new_name,
                        peso=p, cantidad=cant_manual, alto_cm=h_cm,
                        embalaje=tipo_embalaje, embalaje_obs=embalaje_obs,
                        generar_qr=generar_qr_fisico
                    )
                    for av in avisos:
                        st.warning(av)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        if st.session_state.qr_generado:
            st.success("MATERIAL REGISTRADO. ESPERANDO CONFIRMACION FISICA EN EL RACK.")
            st.image(st.session_state.qr_generado, width=200, caption="CODIGO QR LISTO PARA IMPRESION")
            if st.button("LIMPIAR PANTALLA DE IMPRESION"):
                st.session_state.qr_generado = None
                st.rerun()

        # ── Historial (solo admin) ────────────────────────────────
        if _es_admin_m:
          with _st[1]:
            st.subheader("Historial de movimientos")
            try:
                res_h = requests.get(HISTORIAL_URL, timeout=5)
                hist  = res_h.json() if res_h.status_code == 200 and res_h.json() else {}
            except Exception:
                hist = {}

            if hist:
                filas_h = []
                for k, v in sorted(hist.items(), reverse=True):
                    filas_h.append({
                        "Fecha/Hora": v.get('timestamp',''),
                        "Accion":     v.get('accion',''),
                        "ID Pallet":  v.get('uid',''),
                        "Detalle":    v.get('detalle',''),
                        "Rol":        v.get('rol',''),
                    })
                df_h = pd.DataFrame(filas_h)
                # Filtro rapido por accion
                f_acc = st.selectbox("Filtrar por accion",
                    ["TODAS","ALTA","EDICION","BAJA","ELIMINACION","ESCANEO"],
                    index=0, key="filtro_hist")
                if f_acc != "TODAS":
                    df_h = df_h[df_h["Accion"] == f_acc]
                st.caption(f"{len(df_h)} eventos")
                st.dataframe(df_h, use_container_width=True,
                             hide_index=True,
                             height=44 + min(len(df_h), 15) * 36,
                             column_config={
                                 "Fecha/Hora": st.column_config.TextColumn(width="medium"),
                                 "Accion":     st.column_config.TextColumn(width="small"),
                                 "ID Pallet":  st.column_config.TextColumn(width="medium"),
                                 "Detalle":    st.column_config.TextColumn(width="large"),
                                 "Rol":        st.column_config.TextColumn(width="small"),
                             })
                if st.button("Limpiar historial", type="secondary"):
                    requests.put(HISTORIAL_URL, json={}, timeout=5)
                    st.success("Historial limpiado.")
                    st.rerun()
            else:
                st.info("No hay movimientos registrados todavia.")

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
                                registrar_movimiento('ESCANEO', uid_pallet,
                                    f"{item['nombre']} | Rack: {item['rack']}")
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
                    ok, msg, avisos_sc = registrar_pallet(
                        uid=st.session_state.sku_pendiente,
                        sku_base=sku_base, nombre=nom,
                        peso=peso, cantidad=cant, alto_cm=h,
                    )
                    for av in avisos_sc:
                        st.warning(av)
                    if ok:
                        st.session_state.sku_pendiente = None
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

    with tabs[1]:
        import datetime as _dt
        st.subheader("ALTA RAPIDA DE MATERIAL")
        db_movil = cargar_db()  # usa cache
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
                ok, msg, avisos_m = registrar_pallet(
                    uid=uid_m, sku_base=sku_m, nombre=nom_m,
                    peso=peso_m, cantidad=cant_m, alto_cm=alto_cm,
                    embalaje=emb_m, generar_qr=gen_qr,
                )
                for av in avisos_m:
                    st.warning(av)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        if st.session_state.qr_generado:
            st.image(st.session_state.qr_generado, width=220, caption="QR listo")
            if st.button("Limpiar QR"):
                st.session_state.qr_generado = None
                st.rerun()
