"""
ui/escaner.py — Interfaz móvil para escaneo QR y registro de material.
"""
import streamlit as st
import json
import time

def render_escaner():
    """Renderiza la interfaz de escáner móvil con QR."""
    
    st.title("📱 Escáner Móvil")
    st.caption("Escanea códigos QR o busca pallets manualmente")
    
    # Intentar importar el escáner QR
    try:
        from streamlit_qrcode_scanner import qrcode_scanner
        tiene_qr = True
    except ImportError:
        tiene_qr = False
    
    # Tabs para diferentes modos
    if tiene_qr:
        tab1, tab2, tab3 = st.tabs(["📸 Escáner QR", "🔍 Buscar Pallet", "📋 Entrada Manual"])
    else:
        tab1, tab2 = st.tabs(["🔍 Buscar Pallet", "📋 Entrada Manual"])
    
    # TAB 1: Escáner QR (solo si está instalado)
    if tiene_qr:
        with tab1:
            st.subheader("📸 Escáner de Código QR")
            
            # Escáner QR
            qr_code = qrcode_scanner(key='qrcode_mobile')
            
            if qr_code:
                try:
                    # Parsear el código QR
                    data = json.loads(qr_code)
                    mostrar_detalle_pallet(data, True)
                    
                except json.JSONDecodeError:
                    st.error(f"❌ Código QR inválido: `{qr_code}`")
                    st.caption("El código debe ser un JSON válido")
            else:
                st.info("""
                **📸 Instrucciones:**
                
                1. Centra el código QR en el recuadro verde
                2. Espera a que se detecte automáticamente
                3. Revisa los detalles del pallet
                4. Presiona **REGISTRAR ESCANEO** para confirmar
                """)
    
    # TAB: Buscar Pallet (siempre disponible)
    tab_buscar = tab2 if tiene_qr else tab1
    with tab_buscar:
        st.subheader("🔎 Buscar por Matrícula")
        
        matricula_buscar = st.text_input(
            "Matrícula",
            placeholder="Ej: TEST-001",
            key="buscar_matricula"
        )
        
        if st.button("🔍 Buscar", use_container_width=True, type="primary"):
            if matricula_buscar:
                buscar_y_mostrar_pallet(matricula_buscar.strip().upper())
            else:
                st.warning("⚠️ Ingresa una matrícula")
    
    # TAB: Entrada Manual
    tab_manual = tab3 if tiene_qr else tab2
    with tab_manual:
        st.subheader("📝 Ingreso Manual de Datos")
        
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
            
            if st.form_submit_button("💾 Guardar", use_container_width=True, type="primary"):
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
                    st.success(f"✅ Pallet {matricula} registrado!")
                    st.balloons()
                else:
                    st.error("❌ Matrícula y SKU son obligatorios")
    
    # Mensaje si no tiene QR instalado
    if not tiene_qr:
        st.divider()
        st.info("""
        **📸 ¿Quieres usar el escáner QR?**
        
        Instala la librería:
        ```bash
        pip install streamlit-qrcode-scanner
        ```
        Luego reinicia la aplicación.
        """)
    
    # Mostrar historial reciente
    if 'historial_escaneos' in st.session_state and st.session_state.historial_escaneos:
        st.divider()
        st.subheader("📜 Historial Reciente")
        
        for scan in reversed(st.session_state.historial_escaneos[-5:]):
            timestamp = time.strftime('%H:%M:%S', time.localtime(scan['timestamp']))
            st.caption(f"🕒 {timestamp} - {scan['matricula']} ({scan.get('usuario', 'N/A')})")

def mostrar_detalle_pallet(data, mostrar_boton_registro=True):
    """Muestra los detalles de un pallet"""
    matricula = data.get('matricula', 'N/A')
    
    st.success(f"✅ Pallet: **{matricula}**")
    
    # Mostrar detalles
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("SKU", data.get('sku', 'N/A'))
        st.metric("Piezas", data.get('pzas', 'N/A'))
        st.metric("Rack", data.get('rack', 'N/A'))
    
    with col2:
        st.metric("Peso (kg)", data.get('peso', 'N/A'))
        st.metric("Estado", data.get('estado', 'N/A'))
        ubicacion = data.get('ubicacion', {})
        pos = f"P{ubicacion.get('piso','-')}N{ubicacion.get('nivel','-')}C{ubicacion.get('columna','-')}"
        st.metric("Ubicación", pos)
    
    # Detalles completos
    with st.expander("📋 Ver JSON completo"):
        st.json(data)
    
    # Botón de registro
    if mostrar_boton_registro:
        st.divider()
        if st.button("✅ REGISTRAR ESCANEO", use_container_width=True, type="primary", key=f"btn_reg_{matricula}"):
            registrar_escaneo(data)
            st.success("🎉 Escaneo registrado!")
            st.balloons()
            time.sleep(1)
            st.rerun()

def buscar_y_mostrar_pallet(matricula):
    """Busca un pallet en la DB y muestra sus detalles"""
    from firebase import get_db
    
    db = get_db()
    
    if matricula in db:
        data = db[matricula]
        mostrar_detalle_pallet(data, True)
    else:
        st.error(f"❌ No se encontró el pallet: **{matricula}**")
        st.caption("Verifica la matrícula o usa el formulario de entrada manual")

def registrar_escaneo(data):
    """Registra el escaneo en Firebase y en el historial local"""
    from firebase import get_db, guardar_db
    
    matricula = data.get('matricula')
    
    # Obtener DB
    db = get_db()
    
    if matricula and matricula in db:
        # Actualizar timestamp de último escaneo
        db[matricula]['ultimo_escaneo'] = time.time()
        
        # Guardar en Firebase
        guardar_db(db)
        
        print(f"[ESCANER] Escaneo registrado: {matricula}")
        
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
    from firebase import get_db, guardar_db
    
    db = get_db()
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
    st.title("➕ Alta de Material")
    st.caption("Registra un nuevo pallet desde tu móvil")
    
    # Redirigir a la pestaña de entrada manual del escáner
    st.info("""
    **💡 Tip:**
    
    Para dar de alta un nuevo pallet, usa la pestaña **"📋 Entrada Manual"** 
    en la sección de Escáner Móvil.
    
    O usa la versión de escritorio en **Maestro de Artículos** para 
    funcionalidades avanzadas.
    """)
    
    if st.button("📱 Ir a Entrada Manual", use_container_width=True, type="primary"):
        st.switch_page("pages/escaner.py")
