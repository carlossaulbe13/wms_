"""
logica.py — Logica de negocio: asignacion de racks, registro de pallets.
Sin dependencias de UI — funciones puras o que usan session_state minimo.
"""
import time
import datetime
import qrcode
import streamlit as st

from config import (
    CARGA_MAX_NIVEL, PESO_SOBRE, ALTO_LIBRE,
    ALTO_MAX_N1_N2, ALTO_MAX_N3,
    NUM_PISOS, NUM_NIVELES, NUM_COLS,
)
from firebase import guardar_db, registrar_movimiento

# ── Helpers de racks ──────────────────────────────────────────

def rack_stats(db, rack):
    """Retorna (total_items, congelados) para un rack. Excluye artículos de BAJA."""
    items = [v for v in db.values() if v.get('rack') == rack and v.get('estado') != 'BAJA']
    congelados = sum(1 for v in items if v.get('estado') == 'CONGELADO')
    return len(items), congelados

def peso_en_nivel(db, rack, piso, nivel):
    """Suma del peso de todos los items en un nivel específico. Excluye artículos de BAJA."""
    return sum(
        v.get('peso', 0)
        for v in db.values()
        if v.get('rack') == rack
        and v.get('piso') == piso
        and v.get('fila') == nivel
        and v.get('estado') != 'BAJA'
    )

def nivel_acepta_altura(nivel, alto_m):
    """True si el nivel puede alojar un artículo de alto_m metros."""
    if alto_m <= ALTO_LIBRE:
        return True
    if nivel in (1, 2):
        return alto_m <= ALTO_MAX_N1_N2
    if nivel == 3:
        return alto_m <= ALTO_MAX_N3
    return False

def asignar_rack_por_peso_vol(peso, vol):
    """Determina el rack objetivo según peso y volumen."""
    if peso > PESO_SOBRE:
        return "POS_5"
    if peso >= 100:
        return "POS_4"
    if vol > 1.5:
        return "POS_5"
    if peso >= 50 or vol > 1.0:
        return "POS_3"
    if peso >= 20 or vol > 0.5:
        return "POS_2"
    return "POS_1"

def obtener_coordenada_libre(db, rack_objetivo, peso_nuevo=0, alto_m=0):
    """
    Busca la primera posicion libre en el rack respetando:
    - Carga maxima por nivel
    - Restriccion de altura por nivel
    No aplica restricciones en POS_5 (sobredimensiones).
    Excluye posiciones de artículos de BAJA.
    """
    es_sobre = rack_objetivo == "POS_5"
    ocupadas = {
        (v.get('piso'), v.get('fila'), v.get('columna'))
        for v in db.values()
        if v.get('rack') == rack_objetivo and v.get('estado') != 'BAJA'
    }
    for p in range(1, NUM_PISOS + 1):
        for niv in range(1, NUM_NIVELES + 1):
            if not es_sobre and not nivel_acepta_altura(niv, alto_m):
                continue
            if not es_sobre:
                if peso_en_nivel(db, rack_objetivo, p, niv) + peso_nuevo > CARGA_MAX_NIVEL:
                    continue
            for c in range(1, NUM_COLS + 1):
                if (p, niv, c) not in ocupadas:
                    return p, niv, c
    return None, None, None

# ── Registro unificado de pallets ─────────────────────────────

def registrar_pallet(uid, sku_base, nombre, peso, cantidad,
                     alto_cm=0.0, embalaje="", embalaje_obs="",
                     generar_qr=False):
    """
    Registra un pallet aplicando todos los discriminantes.
    Retorna (exito: bool, mensaje: str, avisos: list)
    """
    if not uid or not nombre or not sku_base:
        return False, "Completa ID, SKU y descripcion.", []

    db = st.session_state.db or {}
    if uid in db:
        return False, f"El ID {uid} ya existe en el sistema.", []

    alto_m = alto_cm / 100.0
    avisos = []

    # Discriminante de altura
    if alto_m > ALTO_MAX_N3:
        avisos.append(f"Alto {alto_cm:.0f} cm > 180 cm — asignado a SOBREDIMENSIONES.")
        r = "POS_5"
    elif alto_m > ALTO_MAX_N1_N2:
        avisos.append(f"Alto {alto_cm:.0f} cm > 150 cm — solo nivel 3.")
        r = asignar_rack_por_peso_vol(peso, 0.0)
    else:
        r = asignar_rack_por_peso_vol(peso, 0.0)

    # Discriminante de peso
    if peso > PESO_SOBRE:
        avisos.append(f"Peso {peso:.0f} kg > {PESO_SOBRE:.0f} kg — asignado a SOBREDIMENSIONES.")
        r = "POS_5"

    # Coordenada libre con fallback a sobredimensiones
    piso, nivel, col = obtener_coordenada_libre(db, r, peso_nuevo=peso, alto_m=alto_m)
    if piso is None and r != "POS_5":
        r = "POS_5"
        avisos.append("Rack asignado lleno — redirigido a SOBREDIMENSIONES.")
        piso, nivel, col = obtener_coordenada_libre(db, r, peso_nuevo=peso, alto_m=alto_m)

    if piso is None:
        return False, "Sin espacio disponible en ningun rack. Reorganiza el almacen.", avisos

    # Guardar en Firebase
    fecha = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    st.session_state.db[uid] = {
        "sku_base":      sku_base,
        "nombre":        nombre,
        "peso":          peso,
        "cantidad":      cantidad,
        "volumen":       0.0,
        "alto_m":        round(alto_m, 2),
        "rack":          r,
        "piso":          piso,
        "fila":          nivel,
        "columna":       col,
        "estado":        "ACTIVO",
        "embalaje":      embalaje,
        "embalaje_obs":  embalaje_obs,
        "fecha_llegada": fecha,
    }
    guardar_db(st.session_state.db)
    registrar_movimiento('ALTA', uid,
        f"{nombre} | SKU: {sku_base} | Rack: {r} | Piso {piso} Niv {nivel} Col {col} | {peso}kg")

    # Generar QR
    if generar_qr:
        qr_img = qrcode.make(uid)
        fname  = f"label_{uid}.png"
        qr_img.save(fname)
        st.session_state.qr_generado = fname

    # Activar LED pick-to-light (solo si mqtt_client existe)
    try:
        from mqtt_client import publicar
        publicar(r, "ON")
        time.sleep(0.1)
    except (ImportError, ModuleNotFoundError):
        # MQTT no disponible (Cloud o no configurado)
        print(f"[LOGICA] MQTT no disponible - LED no encendido")
        pass

    # Actualizar estado
    st.session_state.confirmacion_pendiente = r
    st.session_state.rack_resaltado         = r
    st.session_state.rack_resaltado_ts      = time.time()
    st.session_state.twin_zona              = None
    st.session_state.twin_fila              = None

    return True, f"Pallet registrado — Rack: {r} | Piso {piso} | Nivel {nivel} | Col {col}", avisos
