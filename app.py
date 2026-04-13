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

    # KPIs globales
    total_items      = len(db)
    congelados_total = sum(1 for v in db.values() if v.get('estado') == 'CONGELADO')
    activos_total    = total_items - congelados_total
    racks_activos    = len(set(v.get('rack') for v in db.values() if v.get('rack')))

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total pallets", total_items)
    k2.metric("Activos",       activos_total)
    k3.metric("Congelados",    congelados_total)
    k4.metric("Racks en uso",  racks_activos)

    st.markdown("---")

    # Breadcrumb
    zona_sel = st.session_state.twin_zona
    fila_sel = st.session_state.twin_fila

    crumbs = ["Nave principal"]
    if zona_sel: crumbs.append(zona_sel)
    if fila_sel: crumbs.append(fila_sel)
    st.markdown("  ›  ".join(f"**{c}**" for c in crumbs))

    # ── NIVEL 1: Layout de nave ────────────────────────────────
    if zona_sel is None:
        st.subheader("Selecciona una zona del almacen")

        col_rec, col_sobre, col_alma, col_ret = st.columns([1.2, 1.2, 3, 1.2])

        # Recepcion
        with col_rec:
            st.markdown("""
            <div style='background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;
                        padding:20px 10px;text-align:center;color:#cdd3ea;min-height:300px;
                        display:flex;flex-direction:column;align-items:center;
                        justify-content:center;box-sizing:border-box;'>
                <div style='font-size:10px;letter-spacing:2px;color:#8892b0;
                            margin-bottom:12px;'>RECEPCION</div>
                <div style='font-size:13px;color:#8892b0;'>Zona de entrada</div>
            </div>
            """, unsafe_allow_html=True)

        # Sobredimensiones
        with col_sobre:
            t5, c5 = rack_stats(db, "POS_5")
            color_badge = "#dc3545" if c5 > 0 else ("#ffc107" if t5 > 0 else "#3a3f55")
            if st.button(
                f"SOBREDIMENSIONES\n\n{t5} pallets",
                key="btn_sobre", use_container_width=True
            ):
                st.session_state.twin_zona = "SOBREDIMENSIONES"
                st.rerun()
            st.markdown(
                f"<div style='background:#2a2f45;border:2px solid {color_badge};"
                f"border-radius:8px;padding:6px;text-align:center;"
                f"color:#cdd3ea;font-size:11px;margin-top:-8px;'>"
                f"{t5} pallets &nbsp;·&nbsp; {c5} congelados</div>",
                unsafe_allow_html=True
            )

        # Almacenaje — Filas A-D
        with col_alma:
            st.markdown("""
            <div style='background:#1e2130;border:2px dashed #3a3f55;border-radius:10px;
                        padding:8px 12px 12px 12px;'>
            <div style='text-align:center;color:#8892b0;font-size:10px;
                        letter-spacing:2px;margin-bottom:10px;'>ALMACENAJE</div>
            """, unsafe_allow_html=True)

            for fila_label, rack_id in [
                ("FILA A", "POS_1"), ("FILA B", "POS_2"),
                ("FILA C", "POS_3"), ("FILA D", "POS_4")
            ]:
                t, c = rack_stats(db, rack_id)
                ocupacion = min(int(t / 60 * 100), 100)
                color_barra = (
                    "#dc3545" if ocupacion > 80
                    else ("#ffc107" if ocupacion > 50 else "#28a745")
                )
                alerta = " — CONGELADO" if c > 0 else (" — LLENO" if ocupacion >= 100 else "")

                col_btn, col_bar = st.columns([2, 3])
                with col_btn:
                    if st.button(
                        f"{fila_label}{alerta}",
                        key=f"btn_{fila_label}",
                        use_container_width=True
                    ):
                        st.session_state.twin_zona = "ALMACENAJE"
                        st.session_state.twin_fila = fila_label
                        st.rerun()
                with col_bar:
                    st.markdown(
                        f"<div style='margin-top:6px;'>"
                        f"<div style='font-size:10px;color:#8892b0;margin-bottom:3px;'>"
                        f"{t} pallets — {ocupacion}% ocup.</div>"
                        f"<div style='background:#2a2f45;border-radius:4px;height:8px;'>"
                        f"<div style='background:{color_barra};"
                        f"width:{max(ocupacion, 1)}%;height:8px;border-radius:4px;'>"
                        f"</div></div></div>",
                        unsafe_allow_html=True
                    )

            st.markdown("</div>", unsafe_allow_html=True)

        # Retorno
        with col_ret:
            st.markdown("""
            <div style='background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;
                        padding:20px 10px;text-align:center;color:#cdd3ea;min-height:300px;
                        display:flex;flex-direction:column;align-items:center;
                        justify-content:center;box-sizing:border-box;'>
                <div style='font-size:10px;letter-spacing:2px;color:#8892b0;
                            margin-bottom:12px;'>RETORNO</div>
                <div style='font-size:13px;color:#8892b0;'>Devoluciones</div>
            </div>
            """, unsafe_allow_html=True)

        st.caption("Haz clic en una zona o fila para ver el detalle de posiciones.")

    # ── NIVEL 2: Sobredimensiones (POS_5) ─────────────────────
    elif fila_sel is None:
        if st.button("Volver a la nave"):
            st.session_state.twin_zona = None
            st.rerun()

        rack_id = ZONA_A_RACK.get(zona_sel, "POS_5")
        st.subheader(f"Zona: {zona_sel}  |  Rack: {rack_id}")

        items_zona = {k: v for k, v in db.items() if v.get('rack') == rack_id}
        busq = st.text_input("Buscar en esta zona:", "").strip().upper()

        grid_html = "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;'>"
        for fila in range(1, 4):
            for col in range(1, 5):
                item, item_key = None, None
                for k, v in items_zona.items():
                    if v.get('fila') == fila and v.get('columna') == col:
                        item = v; item_key = k; break
                buscado = busq and item and (
                    busq in item.get('nombre', '').upper() or
                    busq in item.get('sku_base', '').upper() or
                    (item_key and busq in item_key.upper())
                )
                bg, border = color_celda(item, buscado)
                if item:
                    grid_html += (
                        f"<div style='background:{bg};border:2px solid {border};"
                        f"border-radius:8px;padding:8px 6px;text-align:center;color:black;"
                        f"height:130px;display:flex;flex-direction:column;"
                        f"justify-content:center;align-items:center;overflow:hidden;box-sizing:border-box;'>"
                        f"<b style='font-size:12px;white-space:nowrap;overflow:hidden;"
                        f"text-overflow:ellipsis;width:95%;display:block;'>{item['nombre']}</b>"
                        f"<span style='font-size:10px;line-height:1.5;'>"
                        f"SKU: {item.get('sku_base','N/A')}<br>"
                        f"<b>{item.get('cantidad',1)} PZAS</b><br>"
                        f"{item.get('estado','ACTIVO')}</span></div>"
                    )
                else:
                    grid_html += (
                        f"<div style='background:{bg};border:2px solid {border};"
                        f"border-radius:8px;padding:8px 6px;text-align:center;color:black;"
                        f"height:130px;display:flex;flex-direction:column;"
                        f"justify-content:center;align-items:center;overflow:hidden;box-sizing:border-box;'>"
                        f"<b style='font-size:12px;'>DISPONIBLE</b>"
                        f"<span style='font-size:10px;color:#555;'>F{fila}-C{col}</span></div>"
                    )
        grid_html += "</div>"
        st.markdown(grid_html, unsafe_allow_html=True)

    # ── NIVEL 3: Fila con posiciones exactas ──────────────────
    else:
        if st.button("Volver a la nave"):
            st.session_state.twin_zona = None
            st.session_state.twin_fila = None
            st.rerun()

        rack_id = ZONA_A_RACK.get(fila_sel, "POS_1")
        st.subheader(f"{fila_sel}  |  Rack: {rack_id}")

        items_fila = {k: v for k, v in db.items() if v.get('rack') == rack_id}
        busq = st.text_input("Buscar material en esta fila:", "").strip().upper()

        grid_html = "<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:6px;'>"
        for fila in range(1, 4):
            for col in range(1, 5):
                item, item_key = None, None
                for k, v in items_fila.items():
                    if v.get('fila') == fila and v.get('columna') == col:
                        item = v; item_key = k; break
                buscado = busq and item and (
                    busq in item.get('nombre', '').upper() or
                    busq in item.get('sku_base', '').upper() or
                    (item_key and busq in item_key.upper())
                )
                bg, border = color_celda(item, buscado)
                if item:
                    congelado    = item.get('estado') == 'CONGELADO'
                    label_estado = "[CONGELADO]" if congelado else item.get('estado', 'ACTIVO')
                    grid_html += (
                        f"<div style='background:{bg};border:2px solid {border};"
                        f"border-radius:8px;padding:8px 6px;text-align:center;color:black;"
                        f"height:130px;display:flex;flex-direction:column;"
                        f"justify-content:center;align-items:center;overflow:hidden;box-sizing:border-box;'>"
                        f"<b style='font-size:12px;white-space:nowrap;overflow:hidden;"
                        f"text-overflow:ellipsis;width:95%;display:block;'>{item['nombre']}</b>"
                        f"<span style='font-size:10px;line-height:1.5;'>"
                        f"SKU: {item.get('sku_base','N/A')}<br>"
                        f"<b>{item.get('cantidad',1)} PZAS</b><br>"
                        f"{label_estado}<br>"
                        f"<span style='color:#666;'>F{fila}-C{col}</span>"
                        f"</span></div>"
                    )
                else:
                    grid_html += (
                        f"<div style='background:{bg};border:2px solid {border};"
                        f"border-radius:8px;padding:8px 6px;text-align:center;color:black;"
                        f"height:130px;display:flex;flex-direction:column;"
                        f"justify-content:center;align-items:center;overflow:hidden;box-sizing:border-box;'>"
                        f"<b style='font-size:12px;'>DISPONIBLE</b>"
                        f"<span style='font-size:10px;color:#555;'>F{fila}-C{col}</span></div>"
                    )
        grid_html += "</div>"
        st.markdown(grid_html, unsafe_allow_html=True)

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
        data_tabla = []
        for k, v in db_actual.items():
            data_tabla.append({
                "MATRICULA (QR)": k,
                "SKU":    v.get('sku_base', 'N/A'),
                "NOMBRE": v.get('nombre', ''),
                "PZAS":   v.get('cantidad', 1),
                "RACK":   v.get('rack', ''),
                "PISO":   v.get('piso', ''),
                "FILA":   v.get('fila', ''),
                "COL":    v.get('columna', ''),
                "ESTADO": v.get('estado', 'ACTIVO')
            })

        df = pd.DataFrame(data_tabla)
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection('single', use_checkbox=True)
        grid_response = AgGrid(
            df, gridOptions=gb.build(),
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            theme='streamlit'
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
