"""
ui/escaner.py — Interfaz móvil para escaneo QR y registro de material.
"""
import streamlit as st
from streamlit_qrcode_scanner import qrcode_scanner
import json
import time

def render_escaner():
    """Renderiza la interfaz de escáner QR móvil con botón de confirmación."""
    
    st.title("📱 Escáner QR")
    st.caption("Escanea el código QR del pallet para ver sus detalles")
    
    # Escáner QR centrado
    qr_code = qrcode_scanner(key='qrcode_mobile')
    
    if qr_code:
        try:
            # Parsear el código QR
            data = json.loads(qr_code)
            matricula = data.get('matricula', 'N/A')
            
            # Guardar en session state
            st.session_state.qr_data_temp = data
            
            # Mostrar detalles del pallet
            st.success(f"✅ Código QR detectado")
            
            st.markdown(f"### 📦 {matricula}")
            
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
            
            st.divider()
            
            # Información adicional
            with st.expander("📋 Ver JSON completo"):
                st.json(data)
            
            st.divider()
            
            # Botón grande para confirmar registro
            if st.button("✅ REGISTRAR ESCANEO", type="primary", use_container_width=True, key="btn_registrar_escaneo"):
                registrar_escaneo(data)
                st.success("🎉 Escaneo registrado exitosamente!")
                st.session_state.qr_data_temp = None
                st.balloons()
                time.sleep(1.5)
                st.rerun()
        
        except json.JSONDecodeError:
            st.error(f"❌ Código QR inválido: `{qr_code}`")
            st.caption("El código debe ser un JSON válido")
    
    else:
        # Instrucciones cuando no hay código
        st.info("""
        **📸 Cómo usar el escáner:**
        
        1. Centra el código QR en el recuadro verde
        2. Espera a que se detecte automáticamente  
        3. Revisa los detalles del pallet
        4. Presiona **REGISTRAR ESCANEO** para confirmar
        """)
        
        # Mostrar historial reciente si existe
        if 'historial_escaneos' in st.session_state and st.session_state.historial_escaneos:
            st.divider()
            st.subheader("📜 Últimos escaneos")
            for scan in reversed(st.session_state.historial_escaneos[-5:]):
                st.caption(f"🕒 {time.strftime('%H:%M:%S', time.localtime(scan['timestamp']))} - {scan['matricula']}")

def registrar_escaneo(data):
    """
    Registra el escaneo del QR en el sistema.
    """
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
    else:
        print(f"[ESCANER] Advertencia: Matrícula {matricula} no encontrada en DB")

def render_alta():
    """Renderiza la interfaz de alta de material (móvil)."""
    st.title("➕ Alta de Material")
    st.caption("Registra un nuevo pallet desde tu móvil")
    
    st.info("""
    **🚧 Función en desarrollo**
    
    Por ahora, usa la versión de escritorio en la pestaña **Maestro de Artículos** para dar de alta material.
    
    **Funcionalidades próximas:**
    - ✨ Captura de datos por voz
    - 📷 Escaneo de código de barras
    - 📸 Cámara para fotos del material
    - ✍️ Firma digital del operador
    """)
    
    st.divider()
    
    # Vista previa del formulario futuro
    with st.expander("👀 Vista previa del formulario"):
        st.text_input("Matrícula", placeholder="Ej: MAT-001", disabled=True)
        st.text_input("SKU", placeholder="Ej: SKU12345", disabled=True)
        st.number_input("Piezas", min_value=1, disabled=True)
        st.number_input("Peso (kg)", min_value=0.0, disabled=True)
        st.button("Registrar", disabled=True, use_container_width=True)
