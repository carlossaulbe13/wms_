"""
ui/login.py — Login con diseño moderno
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN, MQTT_HOST, MQTT_PORT
import json, time, os, socket, requests

_WMS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RFID_JSON_PATH = os.path.join(_WMS_ROOT, "rfid_uid.json")
ES_CLOUD = not os.path.exists(os.path.join(_WMS_ROOT, 'serial_rfid_bridge.py'))

_CSS = """
<style>
/* ── Animaciones RFID ──────────────────── */
@keyframes rfid-glow {
    0%   { box-shadow: 0 6px 22px rgba(0,0,0,0.6); border-color: #48484A; }
    25%  { box-shadow: 0 0 0 10px rgba(245,158,11,0.35), 0 0 48px rgba(245,158,11,0.65); border-color: #F59E0B; }
    60%  { box-shadow: 0 0 0 5px rgba(245,158,11,0.18), 0 0 24px rgba(245,158,11,0.4); border-color: #F59E0B; }
    100% { box-shadow: 0 6px 22px rgba(0,0,0,0.6); border-color: #48484A; }
}
@keyframes rfid-shake {
    0%,100% { transform: translateX(0) rotate(0deg); }
    15%     { transform: translateX(-9px) rotate(-2deg); }
    30%     { transform: translateX(9px)  rotate(2deg); }
    45%     { transform: translateX(-7px) rotate(-1deg); }
    60%     { transform: translateX(7px)  rotate(1deg); }
    75%     { transform: translateX(-4px); }
    90%     { transform: translateX(4px); }
}
.avatar-glow  { animation: rfid-glow  5s ease-out forwards; }
.avatar-shake { animation: rfid-shake 0.65s ease-in-out; }

/* ── Fondo gradiente full-screen ───────── */
[data-testid="stAppViewContainer"] > div:first-child {
    background: linear-gradient(145deg, #111113 0%, #1C1C1E 60%, #2C2C2E 100%);
    min-height: 100vh;
}
[data-testid="stHeader"],
[data-testid="stToolbar"],
[data-testid="stDecoration"],
footer, #MainMenu { display: none !important; }

.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
}

/* ── Card ──────────────────────────────── */
.login-card {
    background: rgba(28, 28, 30, 0.82);
    backdrop-filter: blur(18px);
    -webkit-backdrop-filter: blur(18px);
    border: 1px solid rgba(72, 72, 74, 0.55);
    border-radius: 20px;
    padding: 28px 28px 32px 28px;
    width: 100%;
    box-sizing: border-box;
    box-shadow: 0 16px 48px rgba(0,0,0,0.6);
}

/* ── Input fields ──────────────────────── */
div[data-testid="stForm"] {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}
div[data-testid="stTextInput"] input {
    background: rgba(28, 28, 30, 0.9) !important;
    border: 1px solid #48484A !important;
    border-radius: 10px !important;
    color: #E5E5EA !important;
    font-size: 15px !important;
    padding: 14px 16px !important;
    height: 52px !important;
    caret-color: #E5E5EA !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #F59E0B !important;
    box-shadow: 0 0 0 3px rgba(245,158,11,0.2) !important;
}
div[data-testid="stTextInput"] input::placeholder { color: #48484A !important; }
div[data-testid="stTextInput"] label { display: none !important; }
div[data-testid="stTextInput"] [data-testid="InputInstructions"] { display: none !important; }

/* Toggle ojo contraseña */
div[data-testid="stTextInput"] button {
    background: transparent !important;
    border: none !important;
    color: #F59E0B !important;
}

/* ── Botón submit ──────────────────────── */
div[data-testid="stFormSubmitButton"] > button {
    background: #F59E0B !important;
    color: #111113 !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    letter-spacing: 4px !important;
    font-size: 14px !important;
    width: 100% !important;
    padding: 16px !important;
    height: 52px !important;
    margin-top: 4px !important;
    transition: background 0.2s, color 0.2s !important;
}
div[data-testid="stFormSubmitButton"] > button:hover {
    background: #FBBF24 !important;
    color: #111113 !important;
}

/* ── Mensajes error/success ────────────── */
div[data-testid="stAlert"] {
    border-radius: 10px !important;
    font-size: 13px !important;
    margin-bottom: 14px !important;
}
</style>
"""

_AVATAR_SVG = """
<svg width="40" height="40" viewBox="0 0 24 24" fill="none"
     xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="8" r="4" stroke="#E5E5EA" stroke-width="1.6" fill="none"/>
  <path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"
        stroke="#E5E5EA" stroke-width="1.6" stroke-linecap="round" fill="none"/>
</svg>
"""

@st.cache_data(ttl=10, show_spinner=False)
def _check_sistemas():
    fb_ok = False
    try:
        r = requests.get(
            "https://umad-wms-default-rtdb.firebaseio.com/.json?shallow=true",
            timeout=3,
        )
        fb_ok = r.status_code in (200, 401, 403)
    except Exception:
        pass

    mq_ok = False
    try:
        s = socket.create_connection((MQTT_HOST, MQTT_PORT), timeout=2)
        s.close()
        mq_ok = True
    except Exception:
        pass

    return fb_ok, mq_ok


def _dot(ok: bool) -> str:
    color = "#22C55E"
    glow  = "0 0 8px rgba(34,197,94,0.85)"
    if not ok:
        color = "#3A3A3C"
        glow  = "none"
    return (
        f"<div style='width:7px;height:7px;border-radius:50%;"
        f"background:{color};box-shadow:{glow};flex-shrink:0;'></div>"
    )


def leer_uid_local():
    try:
        if os.path.exists(RFID_JSON_PATH):
            with open(RFID_JSON_PATH, 'r') as f:
                data = json.load(f)
            uid = data.get('uid', '').strip().upper()
            ts  = data.get('timestamp', 0)
            if uid and (time.time() - ts) < 10:
                os.remove(RFID_JSON_PATH)
                return uid
    except Exception:
        pass
    return None

def leer_uid_cloud():
    try:
        from config import RFID_URL
        res = requests.get(RFID_URL, timeout=5)
        if res.status_code != 200:
            return None
        data = res.json()
        if not data or not isinstance(data, dict):
            return None
        uid = data.get('uid', '').strip().upper()
        ts  = data.get('ts', 0)
        if not uid:
            return None
        # Descartar UIDs con más de 4 segundos — evita reprocesar lecturas
        # antiguas tras un logout (session_state se limpia pero Firebase no)
        if (time.time() - ts) >= 4:
            return None
        last_uid = st.session_state.get('_rfid_last_uid', '')
        last_ts  = st.session_state.get('_rfid_last_ts', 0)
        if uid == last_uid and (time.time() - last_ts) < 4:
            return None
        st.session_state['_rfid_last_uid'] = uid
        st.session_state['_rfid_last_ts']  = time.time()
        try:
            requests.delete(RFID_URL, timeout=3)
        except Exception:
            pass
        return uid
    except Exception:
        return None

def _preparar_auth(token_secreto, token_admin_pwd, rol, empleado=None):
    """Devuelve el dict de session_state que aplica la autenticación."""
    if rol == 'admin':
        tok = token_admin_pwd + '_admin'
    else:
        tok = token_secreto + '_' + rol
    return {
        'autenticado':      True,
        'rol':              rol,
        'session_token':    tok,
        '_empleado_activo': empleado,
        '_pwd_bienvenido':  rol,
        '_qs':              tok,
    }


def pantalla_login(token_secreto, token_admin_pwd):
    st_autorefresh(interval=2000, key='login_refresh')
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── 1. Flags de animación de contraseña (leídos ANTES del render) ──
    _pwd_glow  = st.session_state.pop('_pwd_glow_pending', False)
    _pwd_shake = st.session_state.pop('_pwd_shake_pending', False)
    _pwd_error = st.session_state.pop('_pwd_error', None)

    if _pwd_glow:
        # Fase 1: mostrar glow pero NO aplicar auth todavía.
        # El form submit dispara un rerun inmediato; si aplicáramos auth aquí,
        # query_params lanzaría otro rerun y la animación sería invisible.
        # Guardamos la bandera para que el autorefresh (~2s) aplique auth en fase 2.
        st.session_state['_pwd_glow_phase2'] = True
    elif st.session_state.get('_pwd_glow_phase2'):
        # Fase 2 (autorefresh ~2s después): ahora sí aplicar auth y navegar.
        _pwd_glow = True
        st.session_state.pop('_pwd_glow_phase2', None)
        _auth = st.session_state.pop('_pwd_glow_auth', {})
        for _k, _v in _auth.items():
            st.session_state[_k] = _v
        if '_qs' in _auth:
            st.query_params['_s'] = _auth['_qs']

    # ── 2. RFID check ──────────────────────────────────────────
    uid = leer_uid_cloud() if ES_CLOUD else leer_uid_local()
    _rfid_err   = None
    _rfid_glow  = False
    _rfid_shake = False
    _empleado   = None
    if uid:
        if uid in UIDS_AUTORIZADOS:
            _rfid_glow = True
            try:
                from firebase import buscar_empleado_por_uid
                _empleado = buscar_empleado_por_uid(uid)
            except Exception:
                pass
            st.session_state.autenticado      = True
            st.session_state.rol              = (_empleado or {}).get('rol', 'admin')
            st.session_state.session_token    = token_secreto + '_admin'
            st.session_state._empleado_activo = _empleado
            st.query_params['_s']             = token_secreto + '_admin'
        else:
            _rfid_shake = True
            _rfid_err = "Acceso denegado"

    # ── 3. Clase de animación (RFID o contraseña) ──────────────
    _show_glow  = _rfid_glow or _pwd_glow
    _show_shake = not _show_glow and (_rfid_shake or _pwd_shake)
    _anim_class = "avatar-glow" if _show_glow else ("avatar-shake" if _show_shake else "")

    # ── 4. Status dots fijos (esquina inferior izquierda) ────────
    _fb_ok, _mq_ok = _check_sistemas()
    st.markdown(
        f"<div style='position:fixed;bottom:20px;left:20px;display:flex;"
        f"align-items:center;gap:14px;z-index:9999;'>"
        f"  <div style='display:flex;align-items:center;gap:5px;'>"
        f"    {_dot(_fb_ok)}"
        f"    <span style='color:#48484A;font-size:10px;letter-spacing:0.4px;'>Firebase</span>"
        f"  </div>"
        f"  <div style='display:flex;align-items:center;gap:5px;'>"
        f"    {_dot(_mq_ok)}"
        f"    <span style='color:#48484A;font-size:10px;letter-spacing:0.4px;'>MQTT</span>"
        f"  </div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── 5. Layout ──────────────────────────────────────────────
    _, col, _ = st.columns([2, 1, 2])
    with col:
        # ── Bloque 1: título + avatar ──────────────────────────
        st.markdown(
            "<div style='text-align:center;margin-top:6vh;margin-bottom:16px;'>"
            "<span style='color:#E5E5EA;font-size:16px;font-weight:600;"
            "letter-spacing:2.5px;'>WAREHOUSE MANAGEMENT SYSTEM</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"<div class='login-card' style='display:flex;align-items:center;"
            f"justify-content:center;padding:24px;aspect-ratio:1/1;margin-bottom:20px;'>"
            f"<div class='{_anim_class}' style='width:88px;height:88px;background:#111113;"
            f"border:2px solid #2C2C2E;border-radius:50%;"
            f"display:flex;align-items:center;justify-content:center;"
            f"box-shadow:0 4px 16px rgba(0,0,0,0.5);'>"
            f"  {_AVATAR_SVG}"
            f"</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if _show_glow:
            # ── Pantalla de bienvenida (RFID o contraseña) ────
            # En fase 1 del glow de contraseña, _empleado_activo todavía tiene
            # los datos del empleado anterior (auth aún no aplicada). Leer el
            # empleado pendiente directo de _pwd_glow_auth para evitar el flash.
            if _rfid_glow:
                _emp_saludo = _empleado
            elif st.session_state.get('_pwd_glow_auth'):
                _emp_saludo = st.session_state['_pwd_glow_auth'].get('_empleado_activo')
            else:
                _emp_saludo = st.session_state.get('_empleado_activo')
            if _emp_saludo:
                _hon_g  = _emp_saludo.get('honorifico', '')
                _ape_g  = _emp_saludo.get('apellido', '')
                _ape_part = _ape_g.split()[0] if _ape_g else ''
                saludo_nombre = (f"{_hon_g} {_ape_part}".strip() if _ape_part else _emp_saludo.get('nombre', ''))
                pues = _emp_saludo.get('puesto', '')
            else:
                _rol_glow = st.session_state.get('rol', 'admin')
                saludo_nombre = "Administrador" if _rol_glow == 'admin' else "Operador"
                pues = ""

            st.markdown(
                f"<div style='text-align:center;padding:8px 0 20px;'>"
                f"  <div style='color:#F59E0B;font-size:12px;letter-spacing:2px;margin-bottom:6px;'>"
                f"    ACCESO CONCEDIDO</div>"
                f"  <div style='color:#E5E5EA;font-size:22px;font-weight:700;'>"
                f"    Bienvenido de vuelta</div>"
                f"  <div style='color:#F59E0B;font-size:20px;font-weight:600;margin-top:4px;'>"
                f"    {saludo_nombre}</div>"
                + (f"  <div style='color:#6B6B6E;font-size:13px;margin-top:6px;'>{pues}</div>" if pues else "")
                + f"</div>",
                unsafe_allow_html=True,
            )

        else:
            # ── Formulario ────────────────────────────────────
            if _rfid_err:
                st.error(_rfid_err)
            if _pwd_error:
                st.error(_pwd_error)

            with st.form("login_form"):
                pwd    = st.text_input("pwd", type="password", placeholder="Contraseña", label_visibility="collapsed")
                submit = st.form_submit_button("ENTRAR", use_container_width=True)
                if submit:
                    import hashlib as _hl
                    if pwd == PASSWORD_ADMIN:
                        _auth = _preparar_auth(token_secreto, token_admin_pwd, 'admin')
                        st.session_state._pwd_glow_pending = True
                        st.session_state._pwd_glow_auth    = _auth
                        st.rerun()
                    elif pwd == PASSWORD_ACCESO:
                        _auth = _preparar_auth(token_secreto, token_admin_pwd, 'operador')
                        st.session_state._pwd_glow_pending = True
                        st.session_state._pwd_glow_auth    = _auth
                        st.rerun()
                    else:
                        _pwd_hash = _hl.sha256(pwd.encode()).hexdigest()
                        try:
                            from firebase import buscar_empleado_por_password
                            _result = buscar_empleado_por_password(_pwd_hash)
                        except Exception:
                            _result = None
                        if _result:
                            _, _emp = _result
                            _rol = _emp.get('rol', 'operador')
                            _auth = _preparar_auth(token_secreto, token_admin_pwd, _rol, _emp)
                            st.session_state._pwd_glow_pending = True
                            st.session_state._pwd_glow_auth    = _auth
                            st.rerun()
                        else:
                            st.session_state._pwd_shake_pending = True
                            st.session_state._pwd_error         = "Contraseña incorrecta"
                            st.rerun()

