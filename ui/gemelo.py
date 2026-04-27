"""
ui/gemelo.py — Gemelo Digital: vista de nave, racks y drill-down.
"""
import time
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from config import ZONA_A_RACK, NUM_PISOS, NUM_NIVELES, NUM_COLS
from firebase import cargar_db, leer_sensores
from logica import rack_stats
import hashlib as _hashlib

def render(_TOK_ACTIVO):
    """Renderiza el gemelo digital completo."""
    st_autorefresh(interval=4000, key="twin_refresh")
    db = cargar_db(forzar=True)

    # Cargar estados de sensores CNY70 y construir lookup (rack_id, nivel, col) → estado
    _sensores_raw = leer_sensores()
    sensor_estado = {}  # {("POS_1", 1, 1): "ocupado"|"libre"}
    for _lbl, _sdata in (_sensores_raw or {}).items():
        try:
            _p = _lbl.split('-')
            _r = int(_p[0][1:])
            _n = int(_p[1][1:])
            _c = int(_p[2][1:])
            sensor_estado[(f"POS_{_r}", _n, _c)] = (
                _sdata.get('estado', 'libre') if isinstance(_sdata, dict) else 'libre'
            )
        except Exception:
            pass

    # Calculos (necesarios para el layout y los KPIs) - Excluir artículos de BAJA
    db_activos = {k: v for k, v in db.items() if v.get('estado') != 'BAJA'}
    total_items      = len(db_activos)
    congelados_total = sum(1 for v in db_activos.values() if v.get('estado') == 'CONGELADO')
    activos_total    = total_items - congelados_total
    racks_activos    = len(set(v.get('rack') for v in db_activos.values() if v.get('rack')))

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
        badge5 = '#dc3545' if c5 > 0 else '#2d4060'  # solo rojo si hay congelados, neutro si no

        # Resaltado: activo mientras haya confirmacion pendiente (hasta boton fisico)
        rack_res   = st.session_state.get('rack_resaltado')
        res_activo = rack_res is not None and st.session_state.get('confirmacion_pendiente') is not None

        if not res_activo and rack_res is not None:
            st.session_state.rack_resaltado = None

        if res_activo:
            st.markdown("""
            <style>
            @keyframes pulso_amarillo {
                0%,100% { background:#213448; border-color:#547792; box-shadow:none; }
                50%     { background:#713f12; border-color:#facc15;
                          box-shadow:0 0 18px 4px rgba(250,204,21,0.55); }
            }
            .fila-res { animation: pulso_amarillo 2s ease-in-out infinite !important; }
            </style>""", unsafe_allow_html=True)


        CAP_FILA = 45  # 5 racks × 3 niveles × 3 cols
        filas_html = ''
        for fila_label, rack_id in [
            ('FILA A','POS_1'),('FILA B','POS_2'),('FILA C','POS_3'),('FILA D','POS_4')
        ]:
            t, c = rack_stats(db, rack_id)
            a    = t - c  # activos (no congelados)
            occ  = min(round(t / CAP_FILA * 100), 100)
            pct_act  = min(round(a / CAP_FILA * 100), 100)
            pct_cong = min(round(c / CAP_FILA * 100), 100 - pct_act)
            tag  = (' — LLENO' if occ >= 100 else '')
            fenc = fila_label.replace(' ', '+')
            es_res = res_activo and rack_res == rack_id
            clase  = 'fila-res' if es_res else ''
            borde  = '#facc15' if es_res else '#547792'
            # Sensores: contar cuántos están ocupados en esta fila
            _sens_total   = sum(1 for (r, n, cc) in sensor_estado if r == rack_id)
            _sens_ocupados = sum(1 for (r, n, cc), e in sensor_estado.items()
                                 if r == rack_id and e == 'ocupado')
            _badge_sens = (
                f"<span style='background:#ef4444;color:#fff;font-size:9px;"
                f"border-radius:4px;padding:1px 5px;margin-left:6px;'>"
                f"{_sens_ocupados}/{_sens_total} sensor{'es' if _sens_total!=1 else ''}</span>"
                if _sens_total > 0 else ""
            )
            filas_html += (
                f"<a href='?zona=ALMACENAJE&fila={fenc}&_s={_TOK_ACTIVO}' target='_self' "
                f"style='text-decoration:none;display:block;margin-bottom:8px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;'>"
                f"<div class='{clase}' style='flex:0 0 150px;background:#213448;"
                f"border:1.5px solid {borde};"
                f"border-radius:8px;padding:11px 8px;text-align:center;color:#EAE0CF;"
                f"font-size:12px;font-weight:600;cursor:pointer;'>{fila_label}{tag}</div>"
                f"<div style='flex:1;'>"
                f"<div style='font-size:10px;color:#94B4C1;margin-bottom:3px;'>"
                f"{t} pallets — {pct_act}% activos · {pct_cong}% congelados{_badge_sens}</div>"
                f"<div style='background:#1d2e3e;border-radius:4px;height:8px;"
                f"display:flex;overflow:hidden;'>"
                f"<div style='background:#22c55e;width:{pct_act}%;height:8px;flex-shrink:0;'></div>"
                f"<div style='background:#ef4444;width:{pct_cong}%;height:8px;flex-shrink:0;'></div>"
                f"</div></div></div></a>"
            )

        # Clase y borde del botón sobredimensiones
        clase_sobre = 'fila-res' if (res_activo and rack_res == 'POS_5') else ''
        borde_sobre = '#facc15'  if (res_activo and rack_res == 'POS_5') else '#547792'

        nave_html = (
            '<div style="display:grid;grid-template-columns:1fr 1fr 3fr 1fr;gap:8px;align-items:stretch;">'

            '<div style="background:#1d2e3e;border:2px solid #2d4060;border-radius:10px;'
            'padding:16px 10px;text-align:center;color:#EAE0CF;'
            'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
            '<div style="font-size:10px;letter-spacing:2px;color:#94B4C1;margin-bottom:10px;">RECEPCION</div>'
            '<div style="font-size:12px;color:#94B4C1;">Zona de entrada</div>'
            '</div>'

            f'<div style="display:flex;flex-direction:column;gap:6px;">'
            f'<a href="?zona=SOBREDIMENSIONES&_s={_TOK_ACTIVO}" target="_self" style="text-decoration:none;flex:1;display:flex;">'
            f'<div class="{clase_sobre}" '
            f'style="flex:1;background:#213448;border:1.5px solid {borde_sobre};'
            'border-radius:10px;padding:14px 10px;text-align:center;color:#EAE0CF;cursor:pointer;'
            'display:flex;flex-direction:column;align-items:center;justify-content:center;'
            'font-size:12px;font-weight:600;">'
            f'SOBREDIMENSIONES<br><span style="font-size:22px;font-weight:300;margin-top:8px;">{t5}</span>'
            '<span style="font-size:10px;color:#94B4C1;margin-top:2px;">pallets</span>'
            '</div></a>'
            f'<div style="background:#1d2e3e;border:1.5px solid {badge5};border-radius:8px;'
            f'padding:7px;text-align:center;color:#EAE0CF;font-size:11px;">'
            f'{t5} pallets &nbsp;&middot;&nbsp; {c5} congelados</div>'
            '</div>'

            f'<div style="background:#1a2535;border:2px dashed #2d4060;border-radius:10px;'
            'padding:12px 14px;box-sizing:border-box;">'
            '<div style="text-align:center;color:#94B4C1;font-size:10px;'
            'letter-spacing:2px;margin-bottom:12px;">ALMACENAJE</div>'
            f'{filas_html}'
            '</div>'

            '<div style="background:#1d2e3e;border:2px solid #2d4060;border-radius:10px;'
            'padding:16px 10px;text-align:center;color:#EAE0CF;'
            'display:flex;flex-direction:column;align-items:center;justify-content:center;">'
            '<div style="font-size:10px;letter-spacing:2px;color:#94B4C1;margin-bottom:10px;">RETORNO</div>'
            '<div style="font-size:12px;color:#94B4C1;">Devoluciones</div>'
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
            "<div style='display:flex;gap:20px;margin-bottom:14px;font-size:12px;color:#EAE0CF;'>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#1a472a;border-radius:2px;margin-right:4px;'></span>Ocupado</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#7f1d1d;border-radius:2px;margin-right:4px;'></span>Congelado</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#1a2535;border:1px solid #2d4060;border-radius:2px;margin-right:4px;'></span>"
            "Disponible</span>"
            "<span style='color:#94B4C1;'>— Haz clic en un rack para ver el detalle</span>"
            "</div>",
            unsafe_allow_html=True
        )

        NUM_RACKS   = 5
        NUM_NIVELES = 3
        NUM_COLS    = 3
        TOTAL_CELDAS = NUM_NIVELES * NUM_COLS  # 9 por rack

        # SVG de rack como estructura
        def svg_rack_resumen(rack_num, items_rack_local, rack_id_local, sensor_est=None):
            ocupadas = {}
            for k, v in items_rack_local.items():
                if v.get('piso') == rack_num:
                    key = (v.get('fila'), v.get('columna'))
                    ocupadas[key] = v

            total_occ = len(ocupadas)
            occ_pct   = round(total_occ / TOTAL_CELDAS * 100)

            W, H    = 166, 172
            col_w   = 5
            pad_l   = 18  # margen izq desde columna estructural
            pad_r   = 14  # margen der
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
                f"xmlns='http://www.w3.org/2000/svg' style='display:block;margin:0 auto;'>"
                # Columnas estructurales
                f"<rect x='{pad_l-col_w-2}' y='{pad_top-2}' width='{col_w}' height='{H-pad_top-8}' fill='#2d4060'/>"
                f"<rect x='{pad_l+area_w+2}' y='{pad_top-2}' width='{col_w}' height='{H-pad_top-8}' fill='#2d4060'/>"
                # Piso
                f"<rect x='{pad_l-col_w-2}' y='{H-12}' width='{area_w+col_w*2+4}' height='5' fill='#2d4060' rx='1'/>"
                # Labels
                f"<text x='{W//2}' y='16' text-anchor='middle' font-size='10' "
                f"font-weight='600' fill='#EAE0CF' font-family='sans-serif'>RACK {rack_num}</text>"
                f"<text x='{W//2}' y='28' text-anchor='middle' font-size='7' "
                f"fill='#94B4C1' font-family='sans-serif'>{total_occ}/{TOTAL_CELDAS} · {occ_pct}%</text>"
            )

            for ni, nivel in enumerate(range(NUM_NIVELES, 0, -1)):
                y_base = pad_top + ni * est_h
                # Estante
                svg += (
                    f"<line x1='{pad_l-col_w-2}' y1='{y_base + est_h - 3}' "
                    f"x2='{pad_l+area_w+col_w+2}' y2='{y_base + est_h - 3}' "
                    f"stroke='#2d4060' stroke-width='2.5'/>"
                )
                for ci, col in enumerate(range(1, NUM_COLS + 1)):
                    cx = pad_l + ci * cel_w
                    cy = y_base + 2
                    cw = cel_w - 2
                    ch = est_h - 8
                    pos = (nivel, col)

                    if pos in ocupadas:
                        item_v  = ocupadas[pos]
                        _est_v  = item_v.get('estado', 'ACTIVO')
                        _sv     = (sensor_est.get((rack_id_local, nivel, col))
                                   if rack_num == 1 and sensor_est else None)
                        _hs_v   = _sv is not None
                        if _est_v == 'BAJA':
                            if _sv == 'ocupado':
                                bg = '#2a1010'; bord = '#ef4444'; sc = '#f87171'
                            else:
                                bg = '#2d1a00'; bord = '#f59e0b'; sc = '#fbbf24'
                        elif _est_v == 'CONGELADO':
                            bg = '#2a1010'; bord = '#ef4444'; sc = '#f87171'
                        else:
                            if _hs_v and _sv != 'ocupado':
                                bg = '#2d1a00'; bord = '#f59e0b'; sc = '#fbbf24'
                            else:
                                bg = '#1a2a1a'; bord = '#22c55e'; sc = '#4ade80'
                    else:
                        bg = '#1a2535'; bord = '#1d2e3e'; sc = None

                    svg += (
                        f"<rect x='{cx}' y='{cy}' width='{cw}' height='{ch}' "
                        f"rx='2' fill='{bg}' stroke='{bord}' stroke-width='0.8'/>"
                    )
                    if sc:
                        svg += caja_carton(cx, cy, cw, ch, sc)

                    # Dot de sensor (solo piso 1 tiene sensores físicos)
                    if rack_num == 1 and sensor_est:
                        _s = sensor_est.get((rack_id_local, nivel, col))
                        if _s is not None:
                            _dc = '#ef4444' if _s == 'ocupado' else '#22c55e'
                            svg += (
                                f"<circle cx='{cx+cw-4}' cy='{cy+4}' r='3' "
                                f"fill='{_dc}' opacity='0.95'/>"
                            )

            svg += "</svg>"
            return svg, total_occ, occ_pct

        # Renderizar los 5 racks — el SVG completo es el enlace
        racks_grid = "<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:10px;'>"
        for rack_num in range(1, NUM_RACKS + 1):
            svg_r, occ_n, occ_p = svg_rack_resumen(rack_num, items_rack, rack_id, sensor_estado)
            fila_enc = fila_sel.replace(' ', '+')
            url = f"?zona=ALMACENAJE&fila={fila_enc}&rack={rack_num}&_s={_TOK_ACTIVO}"
            racks_grid += (
                f"<a href='{url}' target='_self' style='text-decoration:none;cursor:pointer;'>"
                f"<div style='background:#1a2535;border:1.5px solid #2d4060;"
                f"border-radius:10px;padding:8px 4px;text-align:center;"
                f"transition:border-color 0.15s;'"
                f"onmouseover=\"this.style.borderColor='#94B4C1'\""
                f"onmouseout=\"this.style.borderColor='#2d4060'\">"
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
            "<div style='display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px;font-size:12px;color:#EAE0CF;'>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#1a472a;border:1px solid #22c55e;border-radius:2px;margin-right:4px;'></span>Confirmado (virtual+físico)</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#3d2700;border:1px solid #f59e0b;border-radius:2px;margin-right:4px;'></span>Virtual sin sensor</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#7f1d1d;border:1px solid #ef4444;border-radius:2px;margin-right:4px;'></span>Congelado / BAJA+físico</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#0c3559;border:1px solid #3b9edd;border-radius:2px;margin-right:4px;'></span>"
            "Buscado</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#1a2535;border:1px solid #2d4060;border-radius:2px;margin-right:4px;'></span>"
            "Disponible</span>"
            "<span style='color:#94B4C1;margin-left:8px;'>·</span>"
            "<span style='margin-left:8px;'><span style='display:inline-block;width:10px;height:10px;"
            "background:#22c55e;border-radius:50%;margin-right:4px;'></span>Sensor libre</span>"
            "<span><span style='display:inline-block;width:10px;height:10px;"
            "background:#ef4444;border-radius:50%;margin-right:4px;'></span>Sensor ocupado</span>"
            "<span style='color:#94B4C1;font-size:10px;margin-left:4px;'>(solo rack 1)</span>"
            "</div>",
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
            f"font-weight='600' fill='#EAE0CF' font-family='sans-serif'>"
            f"RACK {rack_sel} — {fila_sel}</text>"
            # Columnas estructurales
            f"<rect x='{pad_l-col_w_d-2}' y='{pad_top}' width='{col_w_d}' height='{H-pad_top-8}' fill='#2d4060' rx='2'/>"
            f"<rect x='{pad_l+area_w+2}' y='{pad_top}' width='{col_w_d}' height='{H-pad_top-8}' fill='#2d4060' rx='2'/>"
            # Piso
            f"<rect x='{pad_l-col_w_d-2}' y='{H-12}' width='{area_w+col_w_d*2+4}' height='6' fill='#2d4060' rx='3'/>"
        )

        for ni, nivel in enumerate(range(NUM_NIVELES, 0, -1)):
            y_base = pad_top + ni * est_h
            # Etiqueta del nivel
            svg += (
                f"<text x='{pad_l-14}' y='{y_base + est_h//2 + 4}' "
                f"text-anchor='end' font-size='9' fill='#94B4C1' font-family='sans-serif'>"
                f"N{nivel}</text>"
            )
            # Linea del estante
            svg += (
                f"<line x1='{pad_l-col_w_d-2}' y1='{y_base + est_h - 3}' "
                f"x2='{pad_l+area_w+col_w_d+2}' y2='{y_base + est_h - 3}' "
                f"stroke='#2d4060' stroke-width='4'/>"
            )
            for ci, col in enumerate(range(1, NUM_COLS + 1)):
                x   = pad_l + (ci) * cel_w
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

                _sensor_val = sensor_estado.get((rack_id, nivel, col)) if rack_sel == 1 else None
                _has_sensor = _sensor_val is not None

                if buscado:
                    color = '#0c3559'; bord = '#3b9edd'
                elif item:
                    _estado = item.get('estado', 'ACTIVO')
                    if _estado == 'BAJA':
                        if _sensor_val == 'ocupado':
                            color = '#7f1d1d'; bord = '#ef4444'
                        else:
                            color = '#3d2700'; bord = '#f59e0b'
                    elif _estado == 'CONGELADO':
                        color = '#7f1d1d'; bord = '#ef4444'
                    else:
                        if _has_sensor and _sensor_val != 'ocupado':
                            color = '#3d2700'; bord = '#f59e0b'
                        else:
                            color = '#1a472a'; bord = '#22c55e'
                else:
                    color = '#1a2535'; bord = '#1d2e3e'

                svg += (
                    f"<rect x='{x}' y='{y}' width='{cw}' height='{ch}' "
                    f"rx='4' fill='{color}' stroke='{bord}' stroke-width='1.5'/>"
                )

                # Etiqueta de posición
                svg += (
                    f"<text x='{x + cw//2}' y='{y_base + 16}' text-anchor='middle' "
                    f"font-size='8' fill='#94B4C1' font-family='sans-serif'>P{col}</text>"
                )

                if item:
                    nom = item.get('nombre','')
                    sku = item.get('sku_base','N/A')
                    pzs = item.get('cantidad', 1)
                    _es_baja = item.get('estado') == 'BAJA'
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
                    if _es_baja:
                        svg += (
                            f"<rect x='{x+2}' y='{y+2}' width='22' height='9' rx='2' fill='#92400e'/>"
                            f"<text x='{x+13}' y='{y+9}' text-anchor='middle' "
                            f"font-size='6' font-weight='700' fill='#fde68a' font-family='sans-serif'>"
                            f"BAJA</text>"
                        )
                else:
                    svg += (
                        f"<text x='{x + cw//2}' y='{y + ch//2 + 4}' text-anchor='middle' "
                        f"font-size='10' fill='#94B4C1' font-family='sans-serif'>LIBRE</text>"
                    )

                if _has_sensor:
                    _dc  = '#ef4444' if _sensor_val == 'ocupado' else '#22c55e'
                    _txt = 'OC' if _sensor_val == 'ocupado' else 'LB'
                    svg += (
                        f"<circle cx='{x+cw-8}' cy='{y+8}' r='7' fill='{_dc}' opacity='0.9'/>"
                        f"<text x='{x+cw-8}' y='{y+12}' text-anchor='middle' "
                        f"font-size='6' font-weight='700' fill='white' font-family='sans-serif'>"
                        f"{_txt}</text>"
                    )

        svg += "</svg>"
        st.markdown(
            f"<div style='background:#1a2535;border:1.5px solid #2d4060;"
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
            f"color:#94B4C1;margin-bottom:4px;'>"
            f"<span>Activos {pct_activos}%</span>"
            f"<span>Congelados {pct_congelados}%</span>"
            f"</div>"
            f"<div style='display:flex;height:10px;border-radius:6px;overflow:hidden;"
            f"background:#1d2e3e;'>"
            f"<div style='width:{pct_activos}%;background:#547792;transition:width 0.4s;'></div>"
            f"<div style='width:{pct_congelados}%;background:#ef4444;transition:width 0.4s;'></div>"
            f"</div></div>",
            unsafe_allow_html=True
        )

    else:
        # Vista de fila: KPIs específicos de esa fila - Excluir artículos de BAJA
        rack_id_kpi = ZONA_A_RACK.get(fila_sel or zona_sel, "POS_1")
        items_fila_kpi = [v for v in db.values() if v.get('rack') == rack_id_kpi and v.get('estado') != 'BAJA']

        total_fila      = len(items_fila_kpi)
        activos_fila    = sum(1 for v in items_fila_kpi if v.get('estado') == 'ACTIVO')
        congelados_fila = sum(1 for v in items_fila_kpi if v.get('estado') == 'CONGELADO')
        cap_total       = 5 * 3 * 3   # 5 pisos × 3 niveles × 3 columnas = 45
        ocupacion_fila  = round(total_fila / cap_total * 100) if cap_total else 0
        peso_total_fila = round(sum(v.get('peso', 0) for v in items_fila_kpi), 1)

        pct_act  = round(activos_fila    / total_fila * 100) if total_fila else 0
        pct_cong = round(congelados_fila / total_fila * 100) if total_fila else 0

        izq, centro, der = st.columns([0.1, 0.8, 0.1])
        with centro:

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
                f"color:#94B4C1;margin-bottom:4px;'>"
                f"<span>Activos {pct_act}%</span>"
                f"<span>Congelados {pct_cong}%</span>"
                f"</div>"
                f"<div style='display:flex;height:10px;border-radius:6px;overflow:hidden;"
                f"background:#1d2e3e;'>"
                f"<div style='width:{pct_act}%;background:#547792;transition:width 0.4s;'></div>"
                f"<div style='width:{pct_cong}%;background:#ef4444;transition:width 0.4s;'></div>"
                f"</div></div>",
                unsafe_allow_html=True
            )
