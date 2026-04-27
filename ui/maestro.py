"""
ui/maestro.py — Maestro de articulos: tabla, edicion e historial.
"""
import os
import streamlit as st
import pandas as pd
import requests
from config import TIPOS_EMBALAJE, HISTORIAL_URL
from firebase import (cargar_db, guardar_db, registrar_movimiento,
                      dar_de_baja_pallet, eliminar_pallet)
from logica import registrar_pallet, asignar_rack_por_peso_vol

def render():
    """Renderiza el maestro de articulos."""
    _es_admin_m = st.session_state.get('rol') == 'admin'
    _subtabs = (["Inventario", "Historial"] if _es_admin_m else ["Inventario"])
    _st = st.tabs(_subtabs)

    with _st[0]:  # Inventario
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
                    "STOCK MIN":      int(v.get('stock_minimo', 0)),
                })
            df_full = pd.DataFrame(data_tabla)

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

            st.caption(f"{len(df_f)} de {len(df_full)} articulos" + (" — selecciona filas para eliminación grupal" if _es_admin_m else ""))

            _df_event = st.dataframe(
                df_f,
                use_container_width=True,
                height=44 + len(df_f) * 36,
                on_select="rerun" if _es_admin_m else "ignore",
                selection_mode="multi-row",
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

            # ── Eliminación grupal (solo admin) ───────────────────
            if _es_admin_m:
                _sel_idx = _df_event.selection.rows if hasattr(_df_event, 'selection') else []
                if _sel_idx:
                    _sel_mats = [df_f.iloc[i]["MATRICULA (QR)"] for i in _sel_idx]
                    _bc1, _bc2 = st.columns([3, 1])
                    with _bc1:
                        st.warning(f"{len(_sel_mats)} artículo(s) seleccionados: {', '.join(_sel_mats[:5])}{'...' if len(_sel_mats)>5 else ''}")
                    with _bc2:
                        if st.button(f"ELIMINAR {len(_sel_mats)} SELEC.", use_container_width=True, type="secondary"):
                            _db_del = cargar_db()
                            for _mat in _sel_mats:
                                if _mat in _db_del:
                                    registrar_movimiento('ELIMINACION', _mat,
                                        f"{_db_del[_mat].get('nombre','')} | BAJA MASIVA")
                                    del _db_del[_mat]
                            guardar_db(_db_del)
                            st.success(f"{len(_sel_mats)} artículo(s) eliminados permanentemente.")
                            st.rerun()

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
                            _nom_b = datos.get('nombre', '')
                            _rack_b = datos.get('rack', '')
                            if dar_de_baja_pallet(uid_sel):
                                registrar_movimiento('BAJA', uid_sel, f"{_nom_b} | {_rack_b}")
                                st.warning(f"Pallet {uid_sel} dado de baja.")
                                st.rerun()
                    with ba3:
                        if st.button("ELIMINAR PERMANENTE", use_container_width=True):
                            _nom_eli  = datos.get('nombre', '')
                            _rack_eli = datos.get('rack', '')
                            if eliminar_pallet(uid_sel):
                                registrar_movimiento('ELIMINACION', uid_sel, f"{_nom_eli} | {_rack_eli}")
                                st.error("Pallet eliminado permanentemente.")
                                st.rerun()
                else:
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
            if 'qr_proveedor_detectado' not in st.session_state:
                st.session_state.qr_proveedor_detectado = False
            if 'generar_qr_fisico' not in st.session_state:
                st.session_state.generar_qr_fisico = True

            st.markdown("**Tipo de embalaje**")
            tipos_embalaje_filtrados = [
                "Pallet americano (1219x1016 mm)",
                "Pallet europeo / EUR (1200x800 mm)",
                "Pallet industrial (1200x1000 mm)",
                "Pallet semilla (1200x1200 mm)",
                "Personalizado",
            ]
            emb1, emb2 = st.columns(2)
            with emb1:
                tipo_embalaje_sel = st.selectbox("Selecciona el tipo", tipos_embalaje_filtrados, key="tipo_emb_pre")
            with emb2:
                embalaje_obs_pre = st.text_input("Observaciones (opcional)", "", key="emb_obs_pre")

            es_personalizado = tipo_embalaje_sel == "Personalizado"
            if es_personalizado:
                st.info(" Has seleccionado embalaje personalizado. Podrás editar las dimensiones (largo, ancho, alto) en el formulario.")
            else:
                st.info(f"✓ Embalaje estándar seleccionado: {tipo_embalaje_sel}")

            with st.form("new_part_manual"):
                st.markdown("**Identificacion**")
                c_id, c_sk, c_nm = st.columns(3)
                with c_id:
                    new_uid = st.text_input("ID UNICO (EJ. PALLET-010)").upper()
                    if new_uid and (len(new_uid) > 8 or '-' not in new_uid):
                        st.session_state.qr_proveedor_detectado = True
                        st.session_state.generar_qr_fisico = False
                    else:
                        st.session_state.qr_proveedor_detectado = False
                        st.session_state.generar_qr_fisico = True
                with c_sk: new_sku_base = st.text_input("SKU / NUMERO DE PARTE")
                with c_nm: new_name     = st.text_input("DESCRIPCION DEL MATERIAL")

                if st.session_state.qr_proveedor_detectado:
                    st.info(" Código QR del proveedor detectado. Solo completa los datos faltantes.")

                st.markdown("**Dimensiones del material**")
                if es_personalizado:
                    dim1, dim2, dim3 = st.columns(3)
                    with dim1:
                        largo_cm = st.number_input("LARGO (CM)", min_value=0.0, step=1.0, value=100.0, key="largo_pers")
                    with dim2:
                        ancho_cm = st.number_input("ANCHO (CM)", min_value=0.0, step=1.0, value=80.0, key="ancho_pers")
                    with dim3:
                        alto_cm = st.number_input("ALTO (CM)", min_value=0.0, step=1.0,
                                                 help="Determina en qué nivel del rack se almacenará", key="alto_pers")
                else:
                    largo_cm = 0.0
                    ancho_cm = 0.0
                    alto_cm = st.number_input("ALTO DEL MATERIAL (CM)", min_value=0.0, step=1.0,
                                             help="Determina en qué nivel del rack se almacenará", key="alto_std")

                st.markdown("**Peso y cantidad**")
                c_p, c_c = st.columns(2)
                with c_p: p           = st.number_input("PESO TOTAL PALLET (KG)", min_value=0.0, step=1.0)
                with c_c: cant_manual = st.number_input("CANTIDAD DE PIEZAS",     min_value=1, value=1)

                st.markdown("")

                if st.session_state.qr_proveedor_detectado:
                    generar_qr_fisico = st.checkbox(
                        "GENERAR CODIGO QR FISICO",
                        value=False,
                        disabled=True,
                        help="Deshabilitado: ya tienes un código QR del proveedor"
                    )
                else:
                    generar_qr_fisico = st.checkbox("GENERAR CODIGO QR FISICO", value=True)

                submitted = st.form_submit_button("REGISTRAR MATERIAL", use_container_width=True)

                if submitted:
                    if es_personalizado:
                        volumen_m3 = (largo_cm * ancho_cm * alto_cm) / 1000000
                        obs_final = f"L:{largo_cm}cm x A:{ancho_cm}cm x H:{alto_cm}cm"
                        if embalaje_obs_pre:
                            obs_final = f"{obs_final} | {embalaje_obs_pre}"
                    else:
                        volumen_m3 = 0.0
                        obs_final = embalaje_obs_pre

                    ok, msg, avisos = registrar_pallet(
                        uid=new_uid, sku_base=new_sku_base, nombre=new_name,
                        peso=p, cantidad=cant_manual, alto_cm=alto_cm,
                        embalaje=tipo_embalaje_sel,
                        embalaje_obs=obs_final,
                        generar_qr=generar_qr_fisico
                    )
                    for av in avisos:
                        st.warning(av)
                    if ok:
                        st.success(msg)
                        st.session_state.navigate_to_gemelo = True
                        st.rerun()
                    else:
                        st.error(msg)

        if st.session_state.qr_generado:
            st.success(" MATERIAL REGISTRADO. ESPERANDO CONFIRMACIÓN FÍSICA EN EL RACK.")

            col_qr1, col_qr2 = st.columns([1, 2])

            with col_qr1:
                st.image(st.session_state.qr_generado, width=200, caption="CÓDIGO QR LISTO PARA IMPRESIÓN")

            with col_qr2:
                st.markdown("###  Descargar QR")
                st.caption("Haz clic para descargar la etiqueta QR")

                try:
                    with open(st.session_state.qr_generado, "rb") as file:
                        qr_bytes = file.read()

                    st.download_button(
                        label=" DESCARGAR QR",
                        data=qr_bytes,
                        file_name=os.path.basename(st.session_state.qr_generado),
                        mime="image/png",
                        use_container_width=True,
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error al leer QR: {e}")

                st.markdown("")

                if st.button(" LIMPIAR PANTALLA", use_container_width=True):
                    try:
                        if os.path.exists(st.session_state.qr_generado):
                            os.remove(st.session_state.qr_generado)
                    except Exception:
                        pass
                    st.session_state.qr_generado = None
                    st.rerun()

            st.divider()

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
