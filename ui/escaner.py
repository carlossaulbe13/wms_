"""
ui/escaner.py — Interfaz móvil para escaneo QR y registro de material.
"""
import streamlit as st
import streamlit.components.v1 as _stc
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
    
    # CSS: recuadro cuadrado fijo centrado — sin borde inferior
    st.markdown("""
    <style>
    iframe:not([height="0"]) {
        width: 100% !important;
        max-width: 340px !important;
        height: 340px !important;
        display: block !important;
        margin: 0 auto !important;
        border-radius: 12px !important;
        border: none !important;
        outline: 1.5px solid #547792 !important;
        outline-offset: -1px !important;
    }
    /* eliminar margen inferior del contenedor Streamlit del componente */
    div[data-testid="stComponentContainer"] {
        margin-bottom: 0 !important;
        padding-bottom: 0 !important;
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
            # Columna centrada para limitar el ancho del iframe del componente
            _pad1, _qr_col, _pad2 = st.columns([1, 4, 1])
            with _qr_col:
                qr_code = qrcode_scanner(key='qrcode_mobile')

            _stc.html("""<script>
(function(){
    var patched=new WeakSet();
    var CSS=`
        *{box-sizing:border-box!important;}
        html,body{
            margin:0!important;padding:0!important;
            width:100%!important;height:100%!important;
            background:#000!important;overflow:hidden!important;
            position:relative!important;
        }
        video{
            position:absolute!important;
            inset:0!important;
            width:100%!important;height:100%!important;
            object-fit:cover!important;
            display:block!important;
            z-index:0!important;
        }
        canvas{
            position:absolute!important;
            inset:0!important;
            width:100%!important;height:100%!important;
            z-index:1!important;
            opacity:0!important;
        }
        svg{opacity:0!important;pointer-events:none!important;}
        *[data-visualcompletion],*[aria-label*="translate"],
        *[class*="live-text"],*[class*="livetext"],
        img-analysis-result,translate-button{display:none!important;}
    `;
    function doInject(f,doc){
        patched.add(f);
        if(f._innerObs){f._innerObs.disconnect();delete f._innerObs;}
        if(doc.getElementById('_umad_css'))return;
        var s=doc.createElement('style');
        s.id='_umad_css';
        s.textContent=CSS;
        (doc.head||doc.body||doc.documentElement).appendChild(s);
        var vid=doc.querySelector('video');
        if(vid){
            vid.setAttribute('translate','no');
            vid.setAttribute('autocorrect','off');
            vid.setAttribute('autocomplete','off');
            vid.setAttribute('spellcheck','false');
        }
    }
    function inject(f){
        if(patched.has(f))return;
        try{
            var doc=f.contentDocument||f.contentWindow.document;
            if(!doc)return;
            if(!doc.querySelector('video')){
                // Video aún no en DOM (esperando permiso de cámara)
                // Instalar observer DENTRO del iframe para detectar cuando aparece
                if(!f._innerObs){
                    try{
                        f._innerObs=new MutationObserver(function(){
                            if(doc.querySelector('video'))doInject(f,doc);
                        });
                        f._innerObs.observe(
                            doc.documentElement||doc.body,
                            {childList:true,subtree:true}
                        );
                    }catch(e){}
                }
                return;
            }
            doInject(f,doc);
        }catch(e){}
    }
    function sweep(){
        var all=window.parent.document.querySelectorAll('iframe');
        for(var i=0;i<all.length;i++)inject(all[i]);
    }
    try{
        new MutationObserver(sweep).observe(
            window.parent.document.documentElement,
            {childList:true,subtree:true}
        );
    }catch(e){}
    [100,400,900,1800,3500,7000,12000].forEach(function(t){setTimeout(sweep,t);});
})();
</script>""", height=0)

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
                rack = st.selectbox("Rack", ["RACK_1", "RACK_2", "RACK_3", "RACK_4", "RACK_5"])
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
    _rack_raw = data.get('rack', 'N/A')
    try:
        from config import RACK_A_FILA
        fila_label = RACK_A_FILA.get(_rack_raw, _rack_raw)
    except Exception:
        fila_label = _rack_raw
    estado = data.get('estado', 'ACTIVO')
    embalaje = data.get('embalaje') or data.get('tipo_pallet', 'N/A')
    alto_cm  = data.get('alto_cm', 0)

    # Ubicación — Firebase guarda piso/fila/columna como campos directos
    piso_v   = data.get('piso',    '-')
    nivel_v  = data.get('fila',    '-')
    col_v    = data.get('columna', '-')

    st.success(f" Pallet: **{matricula}**")

    # Mostrar detalles
    col1, col2 = st.columns(2)

    with col1:
        st.metric("SKU", sku)
        st.metric("Piezas", pzas)
        st.metric("Fila", fila_label)
        st.metric("Embalaje", embalaje)

    with col2:
        st.metric("Nombre", nombre if len(str(nombre)) < 20 else str(nombre)[:17] + "...")
        st.metric("Peso (kg)", peso)
        st.metric("Estado", estado)
        st.metric("Alto (cm)", alto_cm)

    # Ubicación
    pos = f"P{piso_v} N{nivel_v} C{col_v}"
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
                'rack': _rack_raw,
                'estado': estado,
                'embalaje': embalaje,
                'alto_cm': float(alto_cm),
                'ubicacion': pos
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
                col_a = pallet_actualizado.get('columna', '-')
                st.info(f" **Ubicación asignada:** {rack_asignado} → Piso {piso}, Nivel {nivel}, Columna {col_a}")

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

    if '_form_alta_movil_ver' not in st.session_state:
        st.session_state._form_alta_movil_ver = 0

    with st.form(f"form_alta_movil_{st.session_state._form_alta_movil_ver}"):
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
                st.session_state._form_alta_movil_ver += 1
                st.rerun()
            else:
                st.error(msg)
