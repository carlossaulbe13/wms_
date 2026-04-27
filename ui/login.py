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
/* ── Fondo gradiente ───────────────────── */
[data-testid="stAppViewContainer"] > div:first-child {
    background: linear-gradient(145deg, #213448 0%, #547792 65%, #94B4C1 100%);
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

/* ── Card columna central ──────────────── */
.login-card {
    background: rgba(33, 52, 72, 0.72);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    border: 1px solid rgba(148, 180, 193, 0.25);
    border-radius: 20px;
    padding: 52px 36px 36px 36px;
    max-width: 400px;
    margin: 72px auto 0 auto;
    box-shadow: 0 12px 40px rgba(0,0,0,0.45);
    position: relative;
}

/* ── Input fields ──────────────────────── */
div[data-testid="stForm"] {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
}
div[data-testid="stTextInput"] input {
    background: rgba(33, 52, 72, 0.80) !important;
    border: 1px solid #547792 !important;
    border-radius: 8px !important;
    color: #EAE0CF !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
    caret-color: #EAE0CF !important;
}
div[data-testid="stTextInput"] input:focus {
    border-color: #94B4C1 !important;
    box-shadow: 0 0 0 2px rgba(148,180,193,0.25) !important;
}
div[data-testid="stTextInput"] input::placeholder { color: #547792 !important; }
div[data-testid="stTextInput"] label { display: none !important; }
div[data-testid="stTextInput"] [data-testid="InputInstructions"] { display: none !important; }

/* Toggle ojo contraseña */
div[data-testid="stTextInput"] button {
    background: transparent !important;
    border: none !important;
    color: #94B4C1 !important;
}

/* ── Botón submit ──────────────────────── */
div[data-testid="stFormSubmitButton"] > button {
    background: #547792 !important;
    color: #EAE0CF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    letter-spacing: 3px !important;
    font-size: 13px !important;
    width: 100% !important;
    padding: 12px !important;
    margin-top: 6px !important;
    transition: background 0.2s, color 0.2s !important;
}
div[data-testid="stFormSubmitButton"] > button:hover {
    background: #94B4C1 !important;
    color: #213448 !important;
}

/* ── Mensajes error/success ────────────── */
div[data-testid="stAlert"] {
    border-radius: 8px !important;
    font-size: 13px !important;
    margin-bottom: 10px !important;
}
</style>
"""

_AVATAR_SVG = """
<svg width="40" height="40" viewBox="0 0 24 24" fill="none"
     xmlns="http://www.w3.org/2000/svg">
  <circle cx="12" cy="8" r="4" stroke="#EAE0CF" stroke-width="1.6" fill="none"/>
  <path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"
        stroke="#EAE0CF" stroke-width="1.6" stroke-linecap="round" fill="none"/>
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

def pantalla_login(token_secreto, token_admin_pwd):
    st_autorefresh(interval=2000, key='login_refresh')
    st.markdown(_CSS, unsafe_allow_html=True)

    # RFID check antes del render
    uid = leer_uid_cloud() if ES_CLOUD else leer_uid_local()
    _rfid_err = None
    if uid:
        if uid in UIDS_AUTORIZADOS:
            st.session_state.autenticado    = True
            st.session_state.rol            = 'admin'
            st.session_state.session_token  = token_secreto + '_admin'
            st.query_params['_s']           = token_secreto + '_admin'
            st.rerun()
        else:
            _rfid_err = f"UID no autorizado: {uid}"

    # Layout: columna central estrecha
    _, col, _ = st.columns([1.8, 1, 1.8])
    with col:
        # Avatar + encabezado
        st.markdown(
            f"<div class='login-card'>"
            f"<div style='text-align:center; margin-bottom:28px;'>"
            f"  <div style='width:72px;height:72px;background:#213448;"
            f"       border:2.5px solid #547792;border-radius:50%;"
            f"       margin:0 auto 16px auto;display:flex;align-items:center;"
            f"       justify-content:center;box-shadow:0 4px 18px rgba(0,0,0,0.5);'>"
            f"    {_AVATAR_SVG}"
            f"  </div>"
            f"  <div style='color:#EAE0CF;font-size:22px;font-weight:700;"
            f"       letter-spacing:3px;margin-bottom:4px;'>UMAD WMS</div>"
            f"  <div style='color:#94B4C1;font-size:11px;letter-spacing:2px;'>"
            f"    WAREHOUSE MANAGEMENT SYSTEM</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Indicador RFID
        st.markdown(
            "<div style='background:rgba(84,119,146,0.18);border:1px solid #547792;"
            "border-radius:8px;padding:8px 14px;margin-bottom:18px;"
            "display:flex;align-items:center;gap:10px;'>"
            "<div style='width:7px;height:7px;border-radius:50%;background:#94B4C1;"
            "box-shadow:0 0 7px #94B4C1;flex-shrink:0;'></div>"
            "<span style='color:#94B4C1;font-size:12px;'>Pasa tu tarjeta RFID para acceso rápido</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        if _rfid_err:
            st.error(_rfid_err)

        # Formulario contraseña
        with st.form("login_form"):
            pwd    = st.text_input("pwd", type="password", placeholder="Contraseña", label_visibility="collapsed")
            submit = st.form_submit_button("ENTRAR", use_container_width=True)
            if submit:
                if pwd == PASSWORD_ADMIN:
                    st.session_state.autenticado   = True
                    st.session_state.rol           = 'admin'
                    st.session_state.session_token = token_admin_pwd + '_admin'
                    st.query_params['_s']          = token_admin_pwd + '_admin'
                    st.rerun()
                elif pwd == PASSWORD_ACCESO:
                    st.session_state.autenticado   = True
                    st.session_state.rol           = 'operador'
                    st.session_state.session_token = token_secreto + '_operador'
                    st.query_params['_s']          = token_secreto + '_operador'
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")

        # Cierre del div card
        st.markdown("</div>", unsafe_allow_html=True)
