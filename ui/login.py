"""
ui/login.py — Login con diseño moderno
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
import json, time, os, requests

RFID_JSON_PATH = "rfid_uid.json"
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')

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
    border-radius: 24px;
    padding: 56px 48px 48px 48px;
    margin: 0 auto 0 auto;
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
        if not uid:
            return None
        last_uid = st.session_state.get('_rfid_last_uid', '')
        last_ts  = st.session_state.get('_rfid_last_ts', 0)
        if uid == last_uid and (time.time() - last_ts) < 8:
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
    st_autorefresh(interval=6000, key='login_refresh')
    st.markdown(_CSS, unsafe_allow_html=True)

    # ── 1. Flags de animación de contraseña (leídos ANTES del render) ──
    _pwd_glow  = st.session_state.pop('_pwd_glow_pending', False)
    _pwd_shake = st.session_state.pop('_pwd_shake_pending', False)
    _pwd_error = st.session_state.pop('_pwd_error', None)

    if _pwd_glow:
        # Aplicar la autenticación pendiente ahora (sin rerun)
        # Mismo patrón que RFID: autenticado=True en este render,
        # el autorefresh (2s) navega al app principal.
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
            _rfid_err = f"UID no autorizado: {uid}"

    # ── 3. Clase de animación (RFID o contraseña) ──────────────
    _show_glow  = _rfid_glow or _pwd_glow
    _show_shake = not _show_glow and (_rfid_shake or _pwd_shake)
    _anim_class = "avatar-glow" if _show_glow else ("avatar-shake" if _show_shake else "")

    # ── 4. Layout ──────────────────────────────────────────────
    _, col, _ = st.columns([1.2, 1, 1.2])
    with col:
        st.markdown(
            "<div style='text-align:center;margin-top:6vh;margin-bottom:24px;'>"
            "<span style='color:#E5E5EA;font-size:14px;font-weight:600;"
            "letter-spacing:2.5px;'>WAREHOUSE MANAGEMENT SYSTEM</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f"<div class='login-card'>"
            f"<div style='text-align:center; margin-bottom:28px;'>"
            f"  <div class='{_anim_class}' style='width:88px;height:88px;background:#1C1C1E;"
            f"       border:2.5px solid #48484A;border-radius:50%;"
            f"       margin:0 auto 0 auto;display:flex;align-items:center;"
            f"       justify-content:center;box-shadow:0 6px 22px rgba(0,0,0,0.6);'>"
            f"    {_AVATAR_SVG}"
            f"  </div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if _show_glow:
            # ── Pantalla de bienvenida (RFID o contraseña) ────
            _emp_saludo = _empleado if _rfid_glow else st.session_state.get('_empleado_activo')
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
            # ── Indicador RFID + formulario ───────────────────
            st.markdown(
                "<div style='background:rgba(245,158,11,0.08);border:1px solid rgba(245,158,11,0.3);"
                "border-radius:10px;padding:12px 18px;"
                "display:flex;align-items:center;gap:12px;'>"
                "<div style='width:8px;height:8px;border-radius:50%;background:#F59E0B;"
                "box-shadow:0 0 8px #F59E0B;flex-shrink:0;'></div>"
                "<span style='color:#F59E0B;font-size:13px;'>Pasa tu tarjeta RFID para acceso rápido</span>"
                "</div>"
                "<div style='height:36px;'></div>",
                unsafe_allow_html=True,
            )

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

        # Cierre del div card
        st.markdown("</div>", unsafe_allow_html=True)
