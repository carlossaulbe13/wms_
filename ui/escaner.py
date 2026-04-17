"""
ui/escaner.py — Escaner QR movil y alta rapida de material.
"""
import streamlit as st
import cv2
import numpy as np
from pyzbar.pyzbar import decode
from config import TIPOS_EMBALAJE, TOPIC_PUB, PESO_SOBRE, ALTO_MAX_N3
from firebase import cargar_db, guardar_db, registrar_movimiento
from logica import registrar_pallet
from mqtt_client import publicar
import time, qrcode

def render_escaner():
    """Pestaña escaner de campo."""
    st.subheader("CAPTURA DE PALLET FISICO")

    if st.session_state.sku_pendiente is None:
        # CSS para que la camara se vea cuadrada como lector QR de telefono
        st.markdown("""
        <style>
        /* Contenedor de la camara: cuadrado centrado */
        [data-testid="stCameraInput"] > div {
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        /* Video cuadrado con guias de escaneo */
        [data-testid="stCameraInput"] video,
        [data-testid="stCameraInput"] img {
            width: 300px !important;
            height: 300px !important;
            object-fit: cover !important;
            border-radius: 16px !important;
            border: 2px solid #3a3f55 !important;
        }
        /* Boton de captura centrado */
        [data-testid="stCameraInput"] button {
            margin: 12px auto 0 !important;
            display: block !important;
            width: 300px !important;
            border-radius: 12px !important;
            font-size: 15px !important;
            padding: 10px !important;
        }
        </style>
        """, unsafe_allow_html=True)

        # Marco guia de escaneo encima de la camara
        st.markdown("""
        <div style='width:300px;margin:0 auto 8px;position:relative;'>
          <div style='position:relative;width:300px;height:300px;
                      border-radius:16px;overflow:hidden;
                      background:#0d0f1a;'>
            <!-- Guias de esquina estilo lector QR -->
            <div style='position:absolute;top:16px;left:16px;width:40px;height:40px;
              border-top:3px solid #22c55e;border-left:3px solid #22c55e;
              border-radius:4px 0 0 0;'></div>
            <div style='position:absolute;top:16px;right:16px;width:40px;height:40px;
              border-top:3px solid #22c55e;border-right:3px solid #22c55e;
              border-radius:0 4px 0 0;'></div>
            <div style='position:absolute;bottom:16px;left:16px;width:40px;height:40px;
              border-bottom:3px solid #22c55e;border-left:3px solid #22c55e;
              border-radius:0 0 0 4px;'></div>
            <div style='position:absolute;bottom:16px;right:16px;width:40px;height:40px;
              border-bottom:3px solid #22c55e;border-right:3px solid #22c55e;
              border-radius:0 0 4px 0;'></div>
            <div style='position:absolute;top:50%;left:10%;right:10%;
              height:1px;background:rgba(34,197,94,0.3);'></div>
          </div>
          <p style='text-align:center;color:#8892b0;font-size:12px;
            margin-top:8px;'>Centra el codigo QR en el recuadro</p>
        </div>
        """, unsafe_allow_html=True)

        foto = st.camera_input("", label_visibility="collapsed")
        if foto:
            img = cv2.imdecode(np.asarray(bytearray(foto.read()), dtype=np.uint8), 1)
            # Rotar si viene en orientacion incorrecta
            if img.shape[1] > img.shape[0]:  # si es mas ancha que alta, rotar
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
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



def render_alta():
    """Pestaña alta rapida de material (movil)."""
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

