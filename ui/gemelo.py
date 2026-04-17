"""
ui/gemelo.py — Gemelo Digital: vista de nave, racks y drill-down.
"""
import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from config import ZONA_A_RACK, NUM_PISOS, NUM_NIVELES, NUM_COLS
from firebase import cargar_db, leer_rfid_pendiente
from logica import rack_stats
import hashlib as _hashlib

def render(_TOK_ACTIVO):
    """Renderiza el gemelo digital completo."""
    st_autorefresh(interval=4000, key="twin_refresh")
    db = cargar_db(forzar=True)  # refrescar desde Firebase en cada tick
    st.write(db)

    # Leer UID pendiente de Firebase (publicado por ESP32 via HTTP)
    try:
        _r = requests.get(RFID_URL, timeout=3)
        _rfid_fb = _r.json() if _r.status_code == 200 and _r.json() else None
        if _rfid_fb and isinstance(_rfid_fb, dict):
            _uid_fb = _rfid_fb.get('uid', '').strip().upper()
            _ts_fb  = _rfid_fb.get('ts', 0)
            # Procesar solo si es reciente (menos de 10 segundos)
            if _uid_fb and (time.time() - _ts_fb) < 10:
                st.session_state.uid_rfid_recibido = _uid_fb
                # Limpiar el nodo para no reprocesar
                requests.put(RFID_URL, json=None, timeout=3)
    except Exception:
        pass

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

