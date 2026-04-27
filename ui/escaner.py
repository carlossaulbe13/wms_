"""
ui/escaner.py — Interfaz móvil para escaneo QR y registro de material.
"""
import streamlit as st
import json
import time
import sys
import os

# Asegurar que podemos importar módulos del proyecto
if '/mount/src/wms_' not in sys.path:
    sys.path.insert(0, '/mount/src/wms_')
if os.path.dirname(os.path.dirname(__file__)) not in sys.path:
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

def render_escaner():
    """Renderiza la interfaz de escáner móvil con QR."""
    
    st.title(" Escáner Móvil")
    st.caption("Escanea códigos QR o busca pallets manualmente")
    
    # Banner de confirmación pendiente (igual que en desktop)
    if st.session_state.get('confirmacion_pendiente'):
        rack_pendiente = st.session_state.confirmacion_pendiente
        st.warning(f"ALERTA: **ACCIÓN REQUERIDA:** LED del Rack {rack_pendiente} ENCENDIDO")
        
        if st.button(f" CONFIRMAR — APAGAR LED DE {rack_pendiente}",
                     use_container_width=True, type="primary", key="confirmar_led_mobile"):
            st.session_state.confirmacion_pendiente = None
            st.success("✓ Confirmación registrada")
            time.sleep(1)
            st.rerun()
        
        st.divider()
    
    st.markdown("""
    <style>
    video {
        width: 100% !important;
        height: auto !important;
        aspect-ratio: 4/3 !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 16px rgba(0,0,0,0.4) !important;
        display: block !important;
    }
    canvas {
        width: 100% !important;
        height: auto !important;
        aspect-ratio: 4/3 !important;
        border-radius: 10px !important;
        display: block !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Intentar importar el escáner QR
    try:
        from streamlit_qrcode_scanner import qrcode_scanner
        tiene_qr = True
    except ImportError:
        tiene_qr = False
    
    # Tabs para diferentes modos
    if tiene_qr:
        tab1, tab2, tab3 = st.tabs([" Escáner QR", " Buscar Pallet", " Entrada Manual"])
    else:
        tab1, tab2 = st.tabs([" Buscar Pallet", " Entrada Manual"])
    
    # TAB 1: Escáner QR (solo si está instalado)
    if tiene_qr:
        with tab1:
            st.subheader(" Escáner de Código QR")
            
            # Escáner QR
            qr_code = qrcode_scanner(key='qrcode_mobile')
            
            if qr_code:
                try:
                    # Intentar parsear como JSON
                    data = json.loads(qr_code)
                    mostrar_detalle_pallet(data, True)
                    
                except json.JSONDecodeError:
                    # Si no es JSON, puede ser solo el UID (QR simple)
                    if len(qr_code.strip()) > 0:
                        st.warning(f"ALERTA: QR de texto simple detectado: `{qr_code}`")
                        st.info("Este QR solo contiene un ID. Usa 'Buscar Pallet' para ver sus datos.")
                        
                        # Ofrecer buscar por ese UID
                        if st.button(" Buscar este pallet", key="buscar_qr_simple"):
                            buscar_y_mostrar_pallet(qr_code.strip().upper())
                    else:
                        st.error(f" Código QR inválido o vacío")
                        st.caption("El código debe ser un JSON válido con los datos del pallet")
            else:
                st.caption("Apunta la cámara al código QR del pallet")
    
    # TAB: Buscar Pallet (siempre disponible)
    tab_buscar = tab2 if tiene_qr else tab1
    with tab_buscar:
        st.subheader(" Buscar por Matrícula")
        
        matricula_buscar = st.text_input(
            "Matrícula",
            placeholder="Ej: TEST-001",
            key="buscar_matricula"
        )
        
        if st.button(" Buscar", use_container_width=True, type="primary"):
            if matricula_buscar:
                buscar_y_mostrar_pallet(matricula_buscar.strip().upper())
            else:
                st.warning("ALERTA: Ingresa una matrícula")
    
    # TAB: Entrada Manual
    tab_manual = tab3 if tiene_qr else tab2
    with tab_manual:
        st.subheader(" Ingreso Manual de Datos")
        
        with st.form("form_entrada_manual"):
            matricula = st.text_input("Matrícula", placeholder="TEST-001")
            sku = st.text_input("SKU", placeholder="SKU12345")
            
            col1, col2 = st.columns(2)
            with col1:
                pzas = st.number_input("Piezas", min_value=1, value=1)
                peso = st.number_input("Peso (kg)", min_value=0.0, value=0.0, step=0.1)
            
            with col2:
                rack = st.selectbox("Rack", ["POS_1", "POS_2", "POS_3", "POS_4", "POS_5"])
                estado = st.selectbox("Estado", ["ACTIVO", "CONGELADO"])
            
            if st.form_submit_button(" Guardar", use_container_width=True, type="primary"):
                if matricula and sku:
                    datos = {
                        'matricula': matricula.upper(),
                        'sku': sku.upper(),
                        'pzas': pzas,
                        'peso': peso,
                        'rack': rack,
                        'estado': estado
                    }
                    registrar_entrada_manual(datos)
                    st.success(f" Pallet {matricula} registrado!")
                    st.balloons()
                else:
                    st.error(" Matrícula y SKU son obligatorios")
    
    # Mensaje si no tiene QR instalado
    if not tiene_qr:
        st.divider()
        st.info("""
        ** ¿Quieres usar el escáner QR?**
        
        Instala la librería:
        ```bash
        pip install streamlit-qrcode-scanner
        ```
        Luego reinicia la aplicación.
        """)
    
    # Mostrar historial reciente
    if 'historial_escaneos' in st.session_state and st.session_state.historial_escaneos:
        st.divider()
        st.subheader(" Historial Reciente")
        
        for scan in reversed(st.session_state.historial_escaneos[-5:]):
            timestamp = time.strftime('%H:%M:%S', time.localtime(scan['timestamp']))
            st.caption(f" {timestamp} - {scan['matricula']} ({scan.get('usuario', 'N/A')})")

def mostrar_detalle_pallet(data, mostrar_boton_registro=True):
    """Muestra los detalles de un pallet - Compatible con múltiples formatos de QR"""
    
    # Normalizar campos - soportar múltiples formatos
    matricula = data.get('matricula') or data.get('id_unico', 'N/A')
    sku = data.get('sku') or data.get('sku_base', 'N/A')
    nombre = data.get('nombre') or data.get('descripcion', 'N/A')
    pzas = data.get('pzas') or data.get('cantidad') or data.get('cantidad_piezas', 1)
    peso = data.get('peso') or data.get('peso_kg', 0)
    rack = data.get('rack', 'N/A')
    estado = data.get('estado', 'ACTIVO')
    embalaje = data.get('embalaje') or data.get('tipo_pallet', 'N/A')
    alto_cm = data.get('alto_cm', 0)
    
    # Obtener ubicación
    ubicacion = data.get('ubicacion', {})
    if not ubicacion or not isinstance(ubicacion, dict):
        ubicacion = {}
    
    st.success(f" Pallet: **{matricula}**")
    
    # Mostrar detalles
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("SKU", sku)
        st.metric("Piezas", pzas)
        st.metric("Rack", rack)
        st.metric("Embalaje", embalaje)
    
    with col2:
        st.metric("Nombre", nombre if len(str(nombre)) < 20 else str(nombre)[:17] + "...")
        st.metric("Peso (kg)", peso)
        st.metric("Estado", estado)
        st.metric("Alto (cm)", alto_cm)
        
    # Ubicación
    pos = f"P{ubicacion.get('piso','-')}N{ubicacion.get('nivel','-')}C{ubicacion.get('columna','-')}"
    st.caption(f" Ubicación: {pos}")
    
    # Detalles completos
    with st.expander(" Ver JSON completo"):
        st.json(data)
    
    # Botón de registro
    if mostrar_boton_registro:
        st.divider()
        if st.button(" REGISTRAR ESCANEO", use_container_width=True, type="primary", key=f"btn_reg_{matricula}"):
            # Normalizar datos antes de registrar
            datos_normalizados = {
                'matricula': matricula,
                'sku': sku,
                'nombre': nombre,
                'pzas': int(pzas),
                'peso': float(peso),
                'rack': rack,
                'estado': estado,
                'embalaje': embalaje,
                'alto_cm': float(alto_cm),
                'ubicacion': ubicacion
            }
            
            with st.spinner("Registrando y asignando ubicación..."):
                registrar_escaneo(datos_normalizados)
            
            st.success(" Pallet registrado y ubicación asignada!")
            
            # Recargar datos para mostrar la ubicación asignada
            from firebase import cargar_db
            db = cargar_db(forzar=True)
            if matricula in db:
                pallet_actualizado = db[matricula]
                rack_asignado = pallet_actualizado.get('rack', 'N/A')
                piso = pallet_actualizado.get('piso', '-')
                nivel = pallet_actualizado.get('fila', '-')
                col = pallet_actualizado.get('columna', '-')
                
                st.info(f" **Ubicación asignada:** {rack_asignado} → Piso {piso}, Nivel {nivel}, Columna {col}")
            
            st.balloons()
            time.sleep(2)
            st.rerun()

def buscar_y_mostrar_pallet(matricula):
    """Busca un pallet en la DB y muestra sus detalles"""
    from firebase import cargar_db
    
    db = cargar_db()
    
    if matricula in db:
        data = db[matricula]
        mostrar_detalle_pallet(data, True)
    else:
        st.error(f" No se encontró el pallet: **{matricula}**")
        st.caption("Verifica la matrícula o usa el formulario de entrada manual")

def registrar_escaneo(data):
    """Registra el escaneo en Firebase usando la lógica de asignación automática"""
    from firebase import cargar_db, guardar_db, registrar_movimiento
    from logica import registrar_pallet
    
    matricula = data.get('matricula')
    
    # Obtener DB
    db = cargar_db()
    
    if matricula:
        # Si el pallet ya existe, solo actualizar timestamp
        if matricula in db:
            db[matricula]['ultimo_escaneo'] = time.time()
            guardar_db(db)
            print(f"[ESCANER] Timestamp actualizado: {matricula}")
        else:
            # Si no existe, usar la lógica de registrar_pallet para asignar ubicación
            print(f"[ESCANER] Registrando nuevo pallet: {matricula}")
            
            exito, mensaje, avisos = registrar_pallet(
                uid=matricula,
                sku_base=data.get('sku', 'N/A'),
                nombre=data.get('nombre', 'N/A'),
                peso=float(data.get('peso', 0)),
                cantidad=int(data.get('pzas', 1)),
                alto_cm=float(data.get('alto_cm', 0)),
                embalaje=data.get('embalaje', 'N/A'),
                embalaje_obs='',
                generar_qr=False  # No generar QR físico desde escáner
            )
            
            if exito:
                print(f"[ESCANER] ✓ {mensaje}")
                for aviso in avisos:
                    print(f"[ESCANER] ! {aviso}")
            else:
                print(f"[ESCANER] ✗ Error: {mensaje}")
                st.error(f"Error al registrar: {mensaje}")
                return
        
        # Guardar en historial de session
        if 'historial_escaneos' not in st.session_state:
            st.session_state.historial_escaneos = []
        
        st.session_state.historial_escaneos.append({
            'matricula': matricula,
            'timestamp': time.time(),
            'usuario': st.session_state.get('rol', 'operador')
        })

def registrar_entrada_manual(datos):
    """Registra entrada manual en Firebase"""
    from firebase import cargar_db, guardar_db
    
    db = cargar_db()
    matricula = datos['matricula']
    
    # Agregar campos adicionales
    datos['fecha_alta'] = time.time()
    datos['usuario_alta'] = st.session_state.get('rol', 'operador')
    
    # Si no existe ubicación, asignar vacía
    if 'ubicacion' not in datos:
        datos['ubicacion'] = {'piso': None, 'nivel': None, 'columna': None}
    
    # Guardar en DB
    db[matricula] = datos
    guardar_db(db)
    
    print(f"[ESCANER] Entrada manual registrada: {matricula}")
    
    # Registrar en historial
    if 'historial_escaneos' not in st.session_state:
        st.session_state.historial_escaneos = []
    
    st.session_state.historial_escaneos.append({
        'matricula': matricula,
        'timestamp': time.time(),
        'usuario': st.session_state.get('rol', 'operador')
    })

def render_alta():
    """Renderiza la interfaz de alta de material (móvil)."""
    st.title("Alta de Material")
    st.caption("Registra un nuevo pallet desde el dispositivo móvil")

    from logica import registrar_pallet
    from config import TIPOS_EMBALAJE
    import datetime

    with st.form("form_alta_movil"):
        st.markdown("**Identificación**")
        c1, c2 = st.columns(2)
        with c1:
            new_uid  = st.text_input("ID único (ej. PALLET-010)").upper()
            new_sku  = st.text_input("SKU / Número de parte")
        with c2:
            new_nom  = st.text_input("Descripción del material")
            embalaje = st.selectbox("Tipo de embalaje", TIPOS_EMBALAJE)

        st.markdown("**Peso y dimensiones**")
        c3, c4, c5 = st.columns(3)
        with c3: peso    = st.number_input("Peso total (kg)", min_value=0.0, step=1.0)
        with c4: alto_cm = st.number_input("Alto (cm)", min_value=0.0, step=1.0)
        with c5: cant    = st.number_input("Piezas", min_value=1, value=1)

        submitted = st.form_submit_button("REGISTRAR", use_container_width=True, type="primary")

        if submitted:
            ok, msg, avisos = registrar_pallet(
                uid=new_uid, sku_base=new_sku, nombre=new_nom,
                peso=peso, cantidad=cant, alto_cm=alto_cm,
                embalaje=embalaje, embalaje_obs='', generar_qr=False
            )
            for av in avisos:
                st.warning(av)
            if ok:
                st.success(msg)
                st.session_state.navigate_to_gemelo = True
                st.rerun()
            else:
                st.error(msg)
