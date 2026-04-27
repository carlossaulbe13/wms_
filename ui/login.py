"""
ui/login.py — Login profesional con animacion RFID
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from config import UIDS_AUTORIZADOS, PASSWORD_ACCESO, PASSWORD_ADMIN
import json
import time
import os

RFID_JSON_PATH = "rfid_uid.json"
ES_CLOUD = not os.path.exists('serial_rfid_bridge.py')
ANIM_DURATION = 3.2  # segundos minimos de animacion antes de hacer login


# ── Lectura de UID ────────────────────────────────────────────

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
    except:
        pass
    return None

def leer_uid_cloud():
    try:
        from config import RFID_URL
        import requests
        res = requests.get(RFID_URL, timeout=5)
        print(f"[LOGIN] Firebase status={res.status_code} body={res.text[:120]}")
        if res.status_code != 200:
            return None
        try:
            data = res.json()
        except Exception as je:
            print(f"[LOGIN] JSON parse error: {je}")
            return None
        if not data or not isinstance(data, dict):
            print("[LOGIN] Firebase vacio o null")
            return None
        uid = data.get('uid', '').strip().upper()
        ts  = data.get('ts', 0)
        print(f"[LOGIN] uid='{uid}' ts={ts}")
        if uid:
            try:
                requests.delete(RFID_URL, timeout=3)
            except Exception:
                pass
            return uid
        print("[LOGIN] UID descartado — campo uid vacio")
    except Exception as e:
        print(f"[LOGIN] Error Firebase: {e}")
    return None


# ── HTML: tarjeta RFID animada ────────────────────────────────

def _card_html(state: str, denied_uid: str = '') -> str:
    """
    state: 'idle' | 'authorized' | 'denied'
    Retorna HTML autocontenido con animacion CSS.
    """
    if state == 'authorized':
        card_bg      = '#031a0e'
        border       = '#22c55e'
        chip         = '#22c55e'
        wave         = 'rgba(34,197,94,0.55)'
        glow         = '0 0 48px rgba(34,197,94,0.55), 0 0 96px rgba(34,197,94,0.25)'
        status_color = '#22c55e'
        status_text  = 'Acceso autorizado'
        anim_class   = 'authorized'
        show_ripple  = True

    elif state == 'denied':
        card_bg      = '#1a0303'
        border       = '#ef4444'
        chip         = '#ef4444'
        wave         = 'rgba(239,68,68,0.5)'
        glow         = '0 0 40px rgba(239,68,68,0.5)'
        status_color = '#ef4444'
        status_text  = f'UID no autorizado{(": " + denied_uid) if denied_uid else ""}'
        anim_class   = 'denied'
        show_ripple  = False

    else:  # idle
        card_bg      = '#0f172a'
        border       = '#1e3a5f'
        chip         = '#1e3a5f'
        wave         = 'rgba(56,189,248,0.18)'
        glow         = 'none'
        status_color = '#475569'
        status_text  = 'Acerca tu tarjeta RFID'
        anim_class   = 'idle'
        show_ripple  = False

    ripple_html = '<div class="ripple"></div>' if show_ripple else ''

    return f"""
<style>
  .rfid-root {{
    box-sizing:border-box;
    display:flex; flex-direction:column;
    align-items:center; justify-content:center;
    height:200px;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    overflow:hidden;
  }}

  .rfid-root .wrapper {{
    position:relative;
    width:200px; height:126px;
    margin-bottom:14px;
  }}

  /* ── Tarjeta ── */
  .card {{
    width:200px; height:126px;
    background:{card_bg};
    border:2px solid {border};
    border-radius:14px;
    position:relative;
    box-shadow:{glow};
    overflow:hidden;
  }}

  /* franja superior decorativa */
  .card::before {{
    content:'';
    position:absolute;
    top:0; left:0;
    width:100%; height:6px;
    background:linear-gradient(90deg, transparent, {border}44, transparent);
  }}

  /* shimmer scan en authorized */
  .authorized .card::after {{
    content:'';
    position:absolute;
    top:0; left:-70%;
    width:50%; height:100%;
    background:linear-gradient(90deg, transparent, rgba(34,197,94,0.15), transparent);
    animation:shimmer 1.2s ease-in-out infinite;
  }}
  @keyframes shimmer {{
    from {{ left:-60%; }}
    to   {{ left:160%; }}
  }}

  /* ── Chip ── */
  .chip {{
    position:absolute;
    left:20px; top:32px;
    width:34px; height:26px;
    background:{chip};
    border-radius:4px;
    opacity:.85;
  }}
  .chip::after {{
    content:'';
    position:absolute;
    top:50%; left:50%;
    transform:translate(-50%,-50%);
    width:20px; height:14px;
    border:1.5px solid rgba(0,0,0,.4);
    border-radius:2px;
  }}

  /* ── Ondas contactless ── */
  .waves {{
    position:absolute;
    right:18px; top:30px;
    display:flex; gap:4px; align-items:center;
  }}
  .wave {{
    width:9px; height:16px;
    border:2.5px solid {wave};
    border-left:none;
    border-radius:0 12px 12px 0;
    opacity:0;
  }}

  /* ── Ripple exterior ── */
  .ripple {{
    position:absolute;
    inset:0;
    border:2px solid {border};
    border-radius:14px;
    animation:rippleOut 1.4s ease-out infinite;
    pointer-events:none;
  }}
  @keyframes rippleOut {{
    0%   {{ transform:scale(1);   opacity:.8; }}
    100% {{ transform:scale(1.28); opacity:0; }}
  }}

  /* ── IDLE: pulso suave ── */
  .idle .card {{
    animation:idlePulse 3s ease-in-out infinite;
  }}
  @keyframes idlePulse {{
    0%,100% {{ border-color:{border}; opacity:.65; }}
    50%     {{ border-color:{border}cc; opacity:1; }}
  }}
  .idle .chip {{
    animation:chipPulse 3s ease-in-out infinite;
  }}
  @keyframes chipPulse {{
    0%,100% {{ opacity:.35; }}
    50%     {{ opacity:.7; }}
  }}
  .idle .wave {{ animation:waveIdle 2.8s ease-in-out infinite; }}
  .idle .wave:nth-child(1) {{ animation-delay:.0s; }}
  .idle .wave:nth-child(2) {{ animation-delay:.25s; }}
  .idle .wave:nth-child(3) {{ animation-delay:.5s; }}
  @keyframes waveIdle {{
    0%,80%,100% {{ opacity:0; }}
    30%         {{ opacity:.35; }}
  }}

  /* ── AUTHORIZED: despertar ── */
  .authorized .card {{
    animation:authGlow 0.7s ease-in-out infinite alternate;
  }}
  @keyframes authGlow {{
    from {{ box-shadow:0 0 30px rgba(34,197,94,.35); }}
    to   {{ box-shadow:0 0 80px rgba(34,197,94,.8), 0 0 120px rgba(34,197,94,.3); }}
  }}
  .authorized .chip {{ opacity:1; }}
  .authorized .wave {{ animation:waveAuth .6s ease-out infinite; opacity:0; }}
  .authorized .wave:nth-child(1) {{ animation-delay:.0s; }}
  .authorized .wave:nth-child(2) {{ animation-delay:.15s; }}
  .authorized .wave:nth-child(3) {{ animation-delay:.3s; }}
  @keyframes waveAuth {{
    0%   {{ opacity:0; transform:scale(.6); }}
    50%  {{ opacity:1; }}
    100% {{ opacity:0; transform:scale(1.5); }}
  }}

  /* ── DENIED: sacudida ── */
  .denied .card {{
    animation:shake .5s ease-in-out 2;
  }}
  @keyframes shake {{
    0%,100% {{ transform:translateX(0); }}
    20%     {{ transform:translateX(-8px); }}
    40%     {{ transform:translateX(8px); }}
    60%     {{ transform:translateX(-5px); }}
    80%     {{ transform:translateX(5px); }}
  }}

  /* ── Texto de estado ── */
  .status {{
    font-size:12px;
    color:{status_color};
    letter-spacing:.6px;
    font-weight:500;
    text-align:center;
    min-height:18px;
  }}
  .authorized .status {{ animation:fadePop .4s ease-out; }}
  @keyframes fadePop {{
    from {{ opacity:0; transform:translateY(4px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
</style>
<div class="rfid-root">
  <div class="wrapper {anim_class}">
    <div class="card">
      <div class="chip"></div>
      <div class="waves">
        <div class="wave"></div>
        <div class="wave"></div>
        <div class="wave"></div>
      </div>
    </div>
    {ripple_html}
  </div>
  <div class="status {anim_class}">{status_text}</div>
</div>"""


# ── Pantalla principal ────────────────────────────────────────

def pantalla_login(token_secreto, token_admin_pwd):

    # Init session keys
    for k, v in [
        ('rfid_state',       'idle'),
        ('rfid_uid_pending', None),
        ('rfid_anim_start',  0.0),
        ('rfid_denied_uid',  ''),
    ]:
        if k not in st.session_state:
            st.session_state[k] = v

    st_autorefresh(interval=2000, key='login_refresh')

    now   = time.time()
    state = st.session_state.rfid_state

    # ── Máquina de estados ────────────────────────────────────
    if state == 'idle':
        uid = leer_uid_cloud()
        if not uid and not ES_CLOUD:
            uid = leer_uid_local()
        if uid:
            if uid in UIDS_AUTORIZADOS:
                st.session_state.rfid_state       = 'authorized'
                st.session_state.rfid_uid_pending = uid
                st.session_state.rfid_anim_start  = now
            else:
                st.session_state.rfid_state      = 'denied'
                st.session_state.rfid_denied_uid = uid
                st.session_state.rfid_anim_start = now
            st.rerun()

    elif state == 'authorized':
        if now - st.session_state.rfid_anim_start >= ANIM_DURATION:
            uid = st.session_state.rfid_uid_pending
            st.session_state.rfid_state       = 'idle'
            st.session_state.rfid_uid_pending = None
            st.session_state.autenticado      = True
            st.session_state.rol              = 'admin'
            tok = token_admin_pwd + '_admin'
            st.session_state.session_token    = tok
            st.query_params['_s']             = tok
            st.rerun()

    elif state == 'denied':
        if now - st.session_state.rfid_anim_start >= ANIM_DURATION:
            st.session_state.rfid_state      = 'idle'
            st.session_state.rfid_denied_uid = ''
            st.rerun()

    state = st.session_state.rfid_state

    # ── CSS global (oculta sidebar en login) ─────────────────
    st.markdown("""
    <style>
    section[data-testid="stSidebar"] { display:none; }
    .main .block-container {
        max-width: 420px !important;
        margin: auto !important;
        padding-top: 56px !important;
    }
    div[data-testid="stForm"] {
        background: #0f172a;
        border: 1px solid #1e293b;
        border-radius: 12px;
        padding: 24px !important;
    }
    div[data-testid="stTextInput"] input {
        background: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f1f5f9 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stTextInput"] input::placeholder { color: #64748b !important; }
    div[data-testid="stTextInput"] input:focus {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 2px rgba(56,189,248,.2) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Cabecera ──────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center; margin-bottom:28px;">
      <div style="font-size:26px; font-weight:800; color:#f1f5f9; letter-spacing:3px;">
        UMAD WMS
      </div>
      <div style="font-size:10px; color:#475569; letter-spacing:4px; margin-top:5px;">
        WAREHOUSE MANAGEMENT SYSTEM
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── LED indicador ─────────────────────────────────────────
    if ES_CLOUD:
        led_color = '#22c55e'
        led_anim  = 'ledG'
        led_label = 'Firebase Cloud'
    else:
        led_color = '#f59e0b'
        led_anim  = 'ledA'
        led_label = 'Modo Local'

    st.markdown(f"""
    <style>
    @keyframes ledG {{
      0%,100% {{ box-shadow:0 0 3px #22c55e, 0 0 6px #22c55e44; }}
      50%     {{ box-shadow:0 0 7px #22c55e, 0 0 14px #22c55e66; }}
    }}
    @keyframes ledA {{
      0%,100% {{ box-shadow:0 0 3px #f59e0b, 0 0 6px #f59e0b44; }}
      50%     {{ box-shadow:0 0 7px #f59e0b, 0 0 14px #f59e0b66; }}
    }}
    </style>
    <div style="
      display:flex; align-items:center; justify-content:center;
      gap:8px; margin-bottom:24px;
    ">
      <div style="
        width:8px; height:8px; border-radius:50%;
        background:{led_color};
        animation:{led_anim} 2s ease-in-out infinite;
      "></div>
      <span style="font-size:11px; color:#64748b; letter-spacing:1.5px;">{led_label}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── Tarjeta animada ───────────────────────────────────────
    denied_uid = st.session_state.get('rfid_denied_uid', '')
    st.html(_card_html(state, denied_uid))

    # ── Divisor ───────────────────────────────────────────────
    st.markdown("""
    <div style="
      display:flex; align-items:center; gap:10px;
      margin: 16px 0 20px;
    ">
      <div style="flex:1; height:1px; background:#1e293b;"></div>
      <span style="
        color:#334155; font-size:10px; letter-spacing:2px; white-space:nowrap;
      ">O INGRESA TU CONTRASEÑA</span>
      <div style="flex:1; height:1px; background:#1e293b;"></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Formulario ────────────────────────────────────────────
    with st.form("login_form", clear_on_submit=True):
        pwd = st.text_input(
            "Contraseña", placeholder="Contraseña de acceso",
            type="password", label_visibility="collapsed"
        )
        submit = st.form_submit_button(
            "INICIAR SESIÓN", use_container_width=True, type="primary"
        )

        if submit:
            if pwd == PASSWORD_ADMIN:
                st.session_state.autenticado   = True
                st.session_state.rol           = 'admin'
                tok = token_admin_pwd + '_admin'
                st.session_state.session_token = tok
                st.query_params['_s']          = tok
                st.rerun()
            elif pwd == PASSWORD_ACCESO:
                st.session_state.autenticado   = True
                st.session_state.rol           = 'operador'
                tok = token_secreto + '_operador'
                st.session_state.session_token = tok
                st.query_params['_s']          = tok
                st.rerun()
            else:
                st.markdown("""
                <div style="
                  color:#ef4444; font-size:12px;
                  text-align:center; margin-top:10px;
                ">Contraseña incorrecta</div>
                """, unsafe_allow_html=True)
