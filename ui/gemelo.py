"""
ui/gemelo.py — Gemelo Digital: vista de nave, racks y drill-down.
"""
import time
import streamlit as st
import requests  # Aseguramos la importación para evitar errores con RFID
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from config import ZONA_A_RACK, NUM_PISOS, NUM_NIVELES, NUM_COLS, RFID_URL
from firebase import cargar_db, leer_rfid_pendiente
from logica import rack_stats
import hashlib as _hashlib

def render(_TOK_ACTIVO):
    """Renderiza el gemelo digital completo."""
    st_autorefresh(interval=4000, key="twin_refresh")
    db = cargar_db(forzar=True)  # refrescar desde Firebase en cada tick

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
    congelados_total = sum(1 for v in db.values() if isinstance(v, dict) and v.get('estado') == 'CONGELADO')
    activos_total    = total_items - congelados_total
    racks_activos    = len(set(v.get('rack') for v in db.values() if isinstance(v, dict) and v.get('rack')))

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
            if 'rack' in qp:
                st.session_state.twin_rack = int(qp['rack'])
            st.query_params.clear()
            st.query_params['_s'] = _TOK_ACTIVO
            st.rerun()

        t5, c5 = rack_stats(db, 'POS_5')
        badge5 = '#dc3545' if c5 > 0 else '#3a3f55'

        rack_res    = st.session_state.get('rack_resaltado')
        ts_res      = st.session_state.get('rack_resaltado_ts', 0.0)
        elapsed     = time.time() - ts_res
        res_activo  = rack_res is not None and elapsed < 5

        if not res_activo and rack_res is not None:
            st.session_state.rack_resaltado    = None
            st.session_state.rack_resaltado_ts = 0.0

        if res_activo:
            st.markdown("""
            <style>
            @keyframes pulso_amarillo {
                0%   { background:#2e3550; border-color:#4a5080; box-shadow:none; }
                30%  { background:#713f12; border-color:#facc15; box-shadow:0 0 18px 4px rgba(250,204,21,0.55); }
                70%  { background:#713f12; border-color:#facc15; box-shadow:0 0 18px 4px rgba(250,204,21,0.55); }
                100% { background:#2e3550; border-color:#4a5080; box-shadow:none; }
            }
            .fila-res { animation: pulso_amarillo 5s ease !important; }
            </style>""", unsafe_allow_html=True)

        filas_html = ''
        for fila_label, rack_id in [('FILA A','POS_1'),('FILA B','POS_2'),('FILA C','POS_3'),('FILA D','POS_4')]:
            t, c = rack_stats(db, rack_id)
            occ = min(int(t / 60 * 100), 100)
            cb  = '#dc3545' if occ > 80 else ('#ffc107' if occ > 50 else '#28a745')
            tag = (' — LLENO' if occ >= 100 else '')
            fenc = fila_label.replace(' ', '+')
            es_res   = res_activo and rack_res == rack_id
            clase    = 'fila-res' if es_res else ''
            borde    = '#facc15' if es_res else '#4a5080'
            filas_html += (
                f"<a href='?zona=ALMACENAJE&fila={fenc}&_s={_TOK_ACTIVO}' target='_self' style='text-decoration:none;display:block;margin-bottom:8px;'>"
                f"<div style='display:flex;align-items:center;gap:10px;'>"
                f"<div class='{clase}' style='flex:0 0 150px;background:#2e3550;border:1.5px solid {borde};border-radius:8px;padding:11px 8px;text-align:center;color:#cdd3ea;font-size:12px;font-weight:600;cursor:pointer;'>{fila_label}{tag}</div>"
                f"<div style='flex:1;'><div style='font-size:10px;color:#8892b0;margin-bottom:3px;'>{t} pallets — {occ}% ocup.</div>"
                f"<div style='background:#2a2f45;border-radius:4px;height:8px;'><div style='background:{cb};width:{max(occ,1)}%;height:8px;border-radius:4px;'></div></div></div></div></a>"
            )

        nave_html = (
            '<div style="display:grid;grid-template-columns:1fr 1fr 3fr 1fr;gap:8px;align-items:stretch;">'
            '<div style="background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;padding:16px 10px;text-align:center;color:#cdd3ea;display:flex;flex-direction:column;align-items:center;justify-content:center;"><div style="font-size:10px;letter-spacing:2px;color:#8892b0;margin-bottom:10px;">RECEPCION</div><div style="font-size:12px;color:#8892b0;">Zona de entrada</div></div>'
            f'<div style="display:flex;flex-direction:column;gap:6px;"><a href="?zona=SOBREDIMENSIONES&_s={_TOK_ACTIVO}" target="_self" style="text-decoration:none;flex:1;display:flex;"><div style="flex:1;background:#2e3550;border:1.5px solid #4a5080;border-radius:10px;padding:14px 10px;text-align:center;color:#cdd3ea;font-size:12px;font-weight:600;">SOBREDIMENSIONES<br><span style="font-size:22px;font-weight:300;margin-top:8px;">{t5}</span><span style="font-size:10px;color:#8892b0;margin-top:2px;">pallets</span></div></a><div style="background:#2a2f45;border:1.5px solid {badge5};border-radius:8px;padding:7px;text-align:center;color:#cdd3ea;font-size:11px;">{t5} pallets &middot; {c5} congelados</div></div>'
            f'<div style="background:#1e2130;border:2px dashed #3a3f55;border-radius:10px;padding:12px 14px;box-sizing:border-box;"><div style="text-align:center;color:#8892b0;font-size:10px;letter-spacing:2px;margin-bottom:12px;">ALMACENAJE</div>{filas_html}</div>'
            '<div style="background:#2a2f45;border:2px solid #3a3f55;border-radius:10px;padding:16px 10px;text-align:center;color:#cdd3ea;display:flex;flex-direction:column;align-items:center;justify-content:center;"><div style="font-size:10px;letter-spacing:2px;color:#8892b0;margin-bottom:10px;">RETORNO</div><div style="font-size:12px;color:#8892b0;">Devoluciones</div></div></div>'
        )
        st.markdown(nave_html, unsafe_allow_html=True)
        st.caption("Haz clic en una zona o fila para ver el detalle de posiciones.")

    # ── NIVEL 2: Sobredimensiones ─────────────────────────────────────────
    elif fila_sel is None:
        crumbs = ["Nave principal", zona_sel]
        st.markdown(" › ".join(f"**{c}**" for c in crumbs))
        if st.button("Volver a la nave"):
            st.session_state.twin_zona = None
            st.rerun()

        rack_id = ZONA_A_RACK.get(zona_sel, "POS_5")
        items_zona = {k: v for k, v in db.items() if isinstance(v, dict) and v.get('rack') == rack_id}
        st.subheader(f"Zona: {zona_sel} | {len(items_zona)} pallets registrados")

        if items_zona:
            filas_sobre = [{"MATRICULA": k, "SKU": v.get('sku_base','N/A'), "NOMBRE": v.get('nombre',''), "ESTADO": v.get('estado','ACTIVO'), "PESO (KG)": v.get('peso',0)} for k, v in items_zona.items()]
            st.dataframe(pd.DataFrame(filas_sobre), use_container_width=True)
        else:
            st.info("No hay materiales en zona de sobredimensiones.")

    # ── NIVEL 3: Vista de 5 racks (resumen) ────────────────────
    elif rack_sel is None:
        crumbs = ["Nave principal", zona_sel, fila_sel]
        st.markdown(" › ".join(f"**{c}**" for c in crumbs))
        if st.button("Volver a la nave"):
            st.session_state.twin_zona = None
            st.session_state.twin_fila = None
            st.rerun()

        rack_id = ZONA_A_RACK.get(fila_sel, "POS_1")
        items_rack = {k: v for k, v in db.items() if isinstance(v, dict) and v.get('rack') == rack_id}

        # [AQUÍ VA TU FUNCIÓN svg_rack_resumen ORIGINAL]
        def svg_rack_resumen(rack_num, items_rack_local, rack_id_local):
            ocupadas = {}
            for k, v in items_rack_local.items():
                if v.get('piso') == rack_num:
                    key = (v.get('fila'), v.get('columna'))
                    ocupadas[key] = v
            total_occ = len(ocupadas)
            occ_pct   = round(total_occ / 9 * 100)
            W, H = 166, 172
            pad_l, pad_top, area_w = 18, 38, 134
            est_h = (H - pad_top - 14) // 3
            cel_w = area_w // 3

            def caja_carton(x, y, cw, ch, sc):
                bw, bh = int(cw * 0.70), int(ch * 0.65)
                th = int(bh * 0.28)
                bx, by = x + (cw - bw) // 2, y + (ch - bh) // 2 + th // 2
                ty = by - th
                mx = bx + bw // 2
                hx, hw, hh, hy = mx - bw // 6, bw // 3, int(bh * 0.18), by + int(bh * 0.30)
                return (f"<rect x='{bx}' y='{by}' width='{bw}' height='{bh}' rx='1' fill='none' stroke='{sc}' stroke-width='1.3'/>"
                        f"<line x1='{bx}' y1='{by}' x2='{bx+bw//4}' y2='{ty}' stroke='{sc}' stroke-width='1.2'/>"
                        f"<line x1='{bx+bw}' y1='{by}' x2='{bx+bw-bw//4}' y2='{ty}' stroke='{sc}' stroke-width='1.2'/>"
                        f"<rect x='{hx}' y='{hy}' width='{hw}' height='{hh}' rx='{hh//2}' fill='none' stroke='{sc}' stroke-width='1.0'/>")

            svg = f"<svg width='{W}' height='{H}' viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' style='display:block;'>"
            svg += f"<rect x='11' y='36' width='5' height='128' fill='#3a3f55'/><rect x='154' y='36' width='5' height='128' fill='#3a3f55'/>"
            svg += f"<text x='{W//2}' y='16' text-anchor='middle' font-size='10' font-weight='600' fill='#cdd3ea'>RACK {rack_num}</text>"
            for ni, nivel in enumerate(range(3, 0, -1)):
                y_base = pad_top + ni * est_h
                svg += f"<line x1='11' y1='{y_base + est_h - 3}' x2='159' y2='{y_base + est_h - 3}' stroke='#3a3f55' stroke-width='2.5'/>"
                for ci, col in enumerate(range(1, 4)):
                    cx, cy = pad_l + ci * cel_w, y_base + 2
                    pos = (nivel, col)
                    if pos in ocupadas:
                        cong = ocupadas[pos].get('estado') == 'CONGELADO'
                        bg, bord, sc = ('#1a2a1a','#22c55e','#4ade80') if not cong else ('#2a1010','#ef4444','#f87171')
                    else:
                        bg, bord, sc = '#16192a', '#2a2f45', None
                    svg += f"<rect x='{cx}' y='{cy}' width='{cel_w-2}' height='{est_h-8}' rx='2' fill='{bg}' stroke='{bord}' stroke-width='0.8'/>"
                    if sc: svg += caja_carton(cx, cy, cel_w-2, est_h-8, sc)
            svg += "</svg>"
            return svg, total_occ, occ_pct

        # --- CENTRADO DEL GRID DE 5 RACKS ---
        _, col_central_grid, _ = st.columns([0.02, 0.96, 0.02])
        with col_central_grid:
            racks_grid = "<div style='display:grid;grid-template-columns:repeat(5,1fr);gap:10px;'>"
            for rn in range(1, 6):
                svg_r, _, _ = svg_rack_resumen(rn, items_rack, rack_id)
                fenc = fila_sel.replace(' ', '+')
                url = f"?zona=ALMACENAJE&fila={fenc}&rack={rn}&_s={_TOK_ACTIVO}"
                racks_grid += f"<a href='{url}' target='_self' style='text-decoration:none;'><div style='background:#16192a;border:1.5px solid #3a3f55;border-radius:10px;padding:8px 4px;'>{svg_r}</div></a>"
            racks_grid += "</div>"
            st.markdown(racks_grid, unsafe_allow_html=True)

    # ── NIVEL 4: Rack seleccionado en detalle ────────────────────
    else:
        rack_id = ZONA_A_RACK.get(fila_sel, "POS_1")
        items_rack = {k: v for k, v in db.items() if isinstance(v, dict) and v.get('rack') == rack_id}
        crumbs = ["Nave principal", zona_sel, fila_sel, f"Rack {rack_sel}"]
        st.markdown(" › ".join(f"**{c}**" for c in crumbs))

        cb1, cb2 = st.columns(2)
        with cb1:
            if st.button("Volver a los racks"):
                st.session_state.twin_rack = None
                st.rerun()
        with cb2:
            busq = st.text_input("Buscar SKU/Nombre:", "").strip().upper()

        # [TODA TU LÓGICA DE SVG DETALLADO AQUÍ]
        W, H = 340, 320
        svg_det = f"<svg width='100%' viewBox='0 0 {W} {H}' xmlns='http://www.w3.org/2000/svg' style='display:block;max-width:340px;margin:0 auto;'>"
        svg_det += f"<text x='{W//2}' y='24' text-anchor='middle' font-size='16' font-weight='600' fill='#cdd3ea'>RACK {rack_sel}</text>"
        svg_det += f"<rect x='20' y='38' width='10' height='274' fill='#3a3f55' rx='2'/><rect x='310' y='38' width='10' height='274' fill='#3a3f55' rx='2'/>"
        svg_det += f"<rect x='20' y='308' width='300' height='6' fill='#3a3f55' rx='3'/>"
        
        for ni, nivel in enumerate(range(3, 0, -1)):
            y_base = 38 + ni * 85
            svg_det += f"<line x1='20' y1='{y_base+82}' x2='320' y2='{y_base+82}' stroke='#3a3f55' stroke-width='4'/>"
            for ci, col in enumerate(range(1, 4)):
                x, y, cw, ch = 32 + ci * 92 + 3, y_base + 5, 86, 70
                item = next((v for v in items_rack.values() if v.get('piso')==rack_sel and v.get('fila')==nivel and v.get('columna')==col), None)
                color, bord = ('#1a472a','#22c55e') if item else ('#16192a','#2a2f45')
                if item and busq and (busq in item.get('sku_base','') or busq in item.get('nombre','')): color, bord = '#0c3559', '#3b9edd'
                svg_det += f"<rect x='{x}' y='{y}' width='{cw}' height='{ch}' rx='4' fill='{color}' stroke='{bord}' stroke-width='1.5'/>"
        svg_det += "</svg>"

        # --- CENTRADO DEL RACK DETALLADO ---
        _, col_cen_det, _ = st.columns([0.2, 0.6, 0.2])
        with col_cen_det:
            st.markdown(f"<div style='background:#16192a;border:1.5px solid #3a3f55;border-radius:12px;padding:16px;'>{svg_det}</div>", unsafe_allow_html=True)

    # ── KPIs — SECCIÓN FINAL ────────────────
    st.markdown("---")
    izq, centro, der = st.columns([0.1, 0.8, 0.1])
    with centro:
        if zona_sel:
            r_id_kpi = ZONA_A_RACK.get(fila_sel or zona_sel, "POS_1")
            i_kpi = [v for v in db.values() if isinstance(v, dict) and v.get('rack') == r_id_kpi]
            total_f = len(i_kpi)
            act_f = sum(1 for v in i_kpi if v.get('estado') == 'ACTIVO')
            cong_f = sum(1 for v in i_kpi if v.get('estado') == 'CONGELADO')
            peso_f = round(sum(v.get('peso',0) for v in i_kpi), 1)
            
            fk1, fk2, fk3, fk4, fk5 = st.columns(5)
            fk1.metric("Pallets", total_f)
            fk2.metric("Activos", act_f)
            fk3.metric("Congelados", cong_f)
            fk4.metric("Ocupación", f"{round(total_f/45*100)}%")
            fk5.metric("Peso (kg)", peso_f)
