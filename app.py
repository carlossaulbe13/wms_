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

# ─────────────────────────────────────────
# CONFIGURACION FIREBASE
# ─────────────────────────────────────────
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"

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
MQTT_HOST  = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT  = 8883
MQTT_USER  = "saul_mqtt"
MQTT_PASS  = "135700/Saul"
TOPIC_PUB  = "almacen/escaneo"
TOPIC_SUB  = "almacen/confirmacion"

if 'msg_mqtt_recibido' not in st.session_state:
    st.session_state.msg_mqtt_recibido = None

def on_message(client, userdata, msg):
    payload = msg.payload.decode('utf-8')
    if payload.endswith("_OFF"):
        st.session_state.msg_mqtt_recibido = payload.replace("_OFF", "")

def obtener_coordenada_libre(db, rack_objetivo):
    ocupadas = [
        (v.get('piso'), v.get('fila'), v.get('columna'))
        for v in db.values()
        if v.get('rack') == rack_objetivo
    ]
    for p in range(1, 6):
        for f in range(1, 4):
            for c in range(1, 5):
                if (p, f, c) not in ocupadas:
                    return p, f, c
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

tabs = st.tabs(["GEMELO DIGITAL", "ESCANER DE CAMPO", "MAESTRO DE ARTICULOS"])

# ══════════════════════════════════════════════════════════════
# PESTANA 0 — GEMELO DIGITAL
# ══════════════════════════════════════════════════════════════
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
        badge5 = '#dc3545' if c5 > 0 else ('#ffc107' if t5 > 0 else '#3a3f55')

        filas_html = ''
        for fila_label, rack_id in [
            ('FILA A','POS_1'),('FILA B','POS_2'),('FILA C','POS_3'),('FILA D','POS_4')
        ]:
            t, c = rack_stats(db, rack_id)
            occ = min(int(t / 60 * 100), 100)
            cb  = '#dc3545' if occ > 80 else ('#ffc107' if occ > 50 else '#28a745')
            tag = (' CONGELADO' if c > 0 else (' LLENO' if occ >= 100 else ''))
            fenc = fila_label.replace(' ', '+')
            filas_html += (
                f"<a href='?zona=ALMACENAJE&fila={fenc}' target='_self' "
                f"style='text-decoration:none;display:block;margin-bottom:8px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;'>"
                f"<div style='flex:0 0 150px;background:#2e3550;border:1.5px solid #4a5080;"
                f"border-radius:8px;padding:11px 8px;text-align:center;color:#cdd3ea;"
                f"font-size:12px;font-weight:600;cursor:pointer;'>{fila_label}{tag}</div>"
                f"<div style='flex:1;'>"
                f"<div style='font-size:10px;color:#8892b0;margin-bottom:3px;'>{t} pallets — {occ}% ocup.</div>"
                f"<div style='background:#2a2f45;border-radius:4px;height:8px;'>"
                f"<div style='background:{cb};width:{max(occ,1)}%;height:8px;border-radius:4px;'></div>"
                f"</div></div></div></a>"
            )

        nave_html = (
            '<div style="display:grid;grid-template-columns:1fr 1fr 3fr 1fr;gap:8px;align-items:stretch;">'

            '<div style="background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;'
            'padding:16px 10px;text-align:center;color:#cdd3ea;'
            'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
            '<div style="font-size:10px;letter-spacing:2px;color:#8892b0;margin-bottom:10px;">RECEPCION</div>'
            '<div style="font-size:12px;color:#8892b0;">Zona de entrada</div>'
            '</div>'

            f'<div style="display:flex;flex-direction:column;gap:6px;">'
            '<a href="?zona=SOBREDIMENSIONES" target="_self" style="text-decoration:none;flex:1;display:flex;">'
            '<div style="flex:1;background:#2e3550;border:1.5px solid #4a5080;border-radius:10px;'
            'padding:14px 10px;text-align:center;color:#cdd3ea;cursor:pointer;'
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
            "<svg width='32' height='32' viewBox='0 0 24 24' fill='none' "
            "xmlns='http://www.w3.org/2000/svg'>"
            "<rect x='2' y='7' width='20' height='14' rx='2' stroke='white' stroke-width='1.5'/>"
            "<path d='M2 10h20' stroke='white' stroke-width='1.5'/>"
            "<path d='M9 10v11' stroke='white' stroke-width='1.5'/>"
            "<path d='M15 10v11' stroke='white' stroke-width='1.5'/>"
            "<path d='M7 7l2-4h6l2 4' stroke='white' stroke-width='1.5' stroke-linejoin='round'/>"
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

    # KPIs — siempre al final, debajo del layout
    st.markdown("---")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total pallets", total_items)
    k2.metric("Activos",       activos_total)
    k3.metric("Congelados",    congelados_total)
    k4.metric("Racks en uso",  racks_activos)

# ══════════════════════════════════════════════════════════════
# PESTANA 1 — ESCANER DE CAMPO
# ══════════════════════════════════════════════════════════════
with tabs[1]:
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
                vol = (l * a * h) / 1_000_000

                if   peso >= 100:              rack = "POS_4"
                elif vol  >  1.5:              rack = "POS_5"
                elif peso >= 50 or vol > 1.0:  rack = "POS_3"
                elif peso >= 20 or vol > 0.5:  rack = "POS_2"
                else:                          rack = "POS_1"

                piso, fila, col_num = obtener_coordenada_libre(st.session_state.db, rack)

                if piso is not None:
                    st.session_state.db[st.session_state.sku_pendiente] = {
                        "sku_base": sku_base, "nombre": nom, "peso": peso,
                        "cantidad": cant, "volumen": vol, "rack": rack,
                        "piso": piso, "fila": fila, "columna": col_num, "estado": "ACTIVO"
                    }
                    guardar_db(st.session_state.db)
                    if st.session_state.mqtt_client:
                        st.session_state.mqtt_client.publish(TOPIC_PUB, f"{rack}_ON")
                    time.sleep(0.1)
                    st.session_state.confirmacion_pendiente = rack
                    st.session_state.sku_pendiente = None
                    st.success("PALLET REGISTRADO EN FIREBASE Y RACK ACTIVADO.")
                    st.rerun()
                else:
                    st.error(f"ERROR OPERATIVO: EL {rack} ESTA COMPLETAMENTE LLENO.")

# ══════════════════════════════════════════════════════════════
# PESTANA 2 — MAESTRO DE ARTICULOS
# ══════════════════════════════════════════════════════════════
with tabs[2]:
    st.header("GESTION DEL INVENTARIO")
    db_actual = cargar_db()

    if db_actual:
        import datetime
        data_tabla = []
        for k, v in db_actual.items():
            data_tabla.append({
                "MATRICULA (QR)": k,
                "SKU":            v.get('sku_base', 'N/A'),
                "NOMBRE":         v.get('nombre', ''),
                "PZAS":           v.get('cantidad', 1),
                "PESO (KG)":      v.get('peso', 0.0),
                "RACK":           v.get('rack', ''),
                "PISO":           v.get('piso', ''),
                "FILA":           v.get('fila', ''),
                "COL":            v.get('columna', ''),
                "ESTADO":         v.get('estado', 'ACTIVO'),
                "FECHA LLEGADA":  v.get('fecha_llegada', 'N/A'),
            })

        df_full = pd.DataFrame(data_tabla)

        # ── Filtros ──────────────────────────────────────────
        st.markdown("#### Filtros")
        fc1, fc2, fc3, fc4 = st.columns(4)
        with fc1:
            f_nombre = st.text_input("Nombre", "").strip().upper()
        with fc2:
            f_sku = st.text_input("Codigo / SKU", "").strip().upper()
        with fc3:
            pesos_disponibles = sorted(df_full["PESO (KG)"].unique().tolist())
            f_peso_max = st.number_input(
                "Peso max (KG)", min_value=0.0,
                value=float(df_full["PESO (KG)"].max()) if len(df_full) else 0.0,
                step=1.0
            )
        with fc4:
            f_estado = st.selectbox("Estado", ["TODOS", "ACTIVO", "CONGELADO"])

        df_filtrado = df_full.copy()
        if f_nombre:
            df_filtrado = df_filtrado[df_filtrado["NOMBRE"].str.upper().str.contains(f_nombre)]
        if f_sku:
            df_filtrado = df_filtrado[
                df_filtrado["SKU"].str.upper().str.contains(f_sku) |
                df_filtrado["MATRICULA (QR)"].str.upper().str.contains(f_sku)
            ]
        if f_peso_max:
            df_filtrado = df_filtrado[df_filtrado["PESO (KG)"] <= f_peso_max]
        if f_estado != "TODOS":
            df_filtrado = df_filtrado[df_filtrado["ESTADO"] == f_estado]

        st.caption(f"{len(df_filtrado)} de {len(df_full)} articulos")

        # ── Tabla con seleccion ───────────────────────────────
        gb = GridOptionsBuilder.from_dataframe(df_filtrado)
        gb.configure_selection('single', use_checkbox=True)
        gb.configure_default_column(resizable=True, sortable=True, filter=True)
        gb.configure_column("NOMBRE",   minWidth=180)
        gb.configure_column("MATRICULA (QR)", minWidth=160)
        grid_response = AgGrid(
            df_filtrado, gridOptions=gb.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme='streamlit', fit_columns_on_grid_load=True
        )

        sel = grid_response['selected_rows']
        if sel is not None and len(sel) > 0:
            item_sel     = sel.iloc[0].to_dict() if isinstance(sel, pd.DataFrame) else sel[0]
            uid_real     = item_sel['MATRICULA (QR)']
            datos_reales = db_actual[uid_real]

            st.divider()
            st.write(f"### EDITANDO MATRICULA: {uid_real}")

            col_ed1, col_ed2, col_ed3 = st.columns(3)
            with col_ed1:
                nuevo_sku    = st.text_input("SKU BASE", value=datos_reales.get('sku_base', ''))
                nuevo_nombre = st.text_input("NOMBRE",   value=datos_reales['nombre'])
            with col_ed2:
                nueva_cant = st.number_input(
                    "PIEZAS", min_value=1, value=int(datos_reales.get('cantidad', 1))
                )
            with col_ed3:
                nuevo_estado = st.selectbox(
                    "ESTADO", ["ACTIVO", "CONGELADO"],
                    index=0 if datos_reales.get('estado') == "ACTIVO" else 1
                )

            st.write("DIMENSIONES Y PESO")
            col_p, col_v = st.columns(2)
            with col_p:
                nuevo_peso = st.number_input(
                    "PESO (KG)", min_value=0.0, value=float(datos_reales.get('peso', 0.0))
                )
            with col_v:
                nuevo_vol = st.number_input(
                    "VOLUMEN (M3)", min_value=0.0,
                    value=float(datos_reales.get('volumen', 0.0)), step=0.1
                )

            rack_actual = datos_reales.get('rack', 'POS_2')
            if   nuevo_peso >= 100:                    rack_ideal = "POS_4"
            elif nuevo_vol  >  1.5:                    rack_ideal = "POS_5"
            elif nuevo_peso >= 50 or nuevo_vol > 1.0:  rack_ideal = "POS_3"
            elif nuevo_peso >= 20 or nuevo_vol > 0.5:  rack_ideal = "POS_2"
            else:                                      rack_ideal = "POS_1"

            if rack_actual != rack_ideal:
                st.warning(
                    f"ALERTA OPERATIVA: Por las nuevas dimensiones/peso, este material "
                    f"deberia reubicarse en {rack_ideal} (actualmente en {rack_actual})."
                )

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("GUARDAR CAMBIOS"):
                    db_actual[uid_real].update({
                        'sku_base': nuevo_sku, 'nombre': nuevo_nombre,
                        'cantidad': nueva_cant, 'estado': nuevo_estado,
                        'peso': nuevo_peso, 'volumen': nuevo_vol
                    })
                    guardar_db(db_actual)
                    st.success("CAMBIOS GUARDADOS.")
                    st.rerun()
            with col_b:
                if st.button("ELIMINAR PALLET DE LA NUBE"):
                    del db_actual[uid_real]
                    guardar_db(db_actual)
                    st.rerun()

    with st.expander("ALTA DE MATERIALES Y ASIGNACION MANUAL"):
        with st.form("new_part_manual"):
            new_uid = st.text_input("ID UNICO DEL PALLET (EJ. PALLET-010)").upper()

            c_sk, c_nm = st.columns(2)
            with c_sk: new_sku_base = st.text_input("SKU GENERICO")
            with c_nm: new_name     = st.text_input("DESCRIPCION")

            c_p, c_c = st.columns(2)
            with c_p: p           = st.number_input("PESO (KG)", min_value=0.0)
            with c_c: cant_manual = st.number_input("CANTIDAD DE PIEZAS", min_value=1, value=1)

            c1, c2, c3 = st.columns(3)
            with c1: l = st.number_input("LARGO (CM)", min_value=0.0)
            with c2: a = st.number_input("ANCHO (CM)", min_value=0.0)
            with c3: h = st.number_input("ALTO (CM)",  min_value=0.0)

            generar_qr_fisico = st.checkbox("GENERAR CODIGO QR FISICO", value=True)

            if st.form_submit_button("REGISTRAR MATERIAL"):
                vol = (l / 100) * (a / 100) * (h / 100)

                if   p >= 100:             r = "POS_4"
                elif vol > 1.5:            r = "POS_5"
                elif p >= 50 or vol > 1.0: r = "POS_3"
                elif p >= 20 or vol > 0.5: r = "POS_2"
                else:                      r = "POS_1"

                piso, fila, columna = obtener_coordenada_libre(st.session_state.db, r)

                if piso is None:
                    st.error(f"ERROR OPERATIVO: EL {r} ESTA LLENO.")
                else:
                    st.session_state.db[new_uid] = {
                        "sku_base": new_sku_base, "nombre": new_name,
                        "peso": p, "cantidad": cant_manual,
                        "volumen": vol, "rack": r,
                        "piso": piso, "fila": fila, "columna": columna, "estado": "ACTIVO"
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
                    st.rerun()

    if st.session_state.qr_generado:
        st.success("MATERIAL REGISTRADO. ESPERANDO CONFIRMACION FISICA EN EL RACK.")
        st.image(st.session_state.qr_generado, width=200, caption="CODIGO QR LISTO PARA IMPRESION")
        if st.button("LIMPIAR PANTALLA DE IMPRESION"):
            st.session_state.qr_generado = None
            st.rerun()
