# UMAD Warehouse Management System (WMS)

Sistema de gestión de almacén con gemelo digital, autenticación RFID y asignación automática de ubicaciones.

## 🏗️ Estructura del Proyecto

```
wms/
├── app.py                    # Punto de entrada principal
├── config.py                 # Configuración y constantes
├── firebase.py               # Operaciones con Firebase
├── logica.py                 # Lógica de negocio y asignación de racks
├── requirements.txt          # Dependencias Python
│
├── ui/
│   ├── login.py             # Pantalla de login (RFID + contraseña)
│   ├── gemelo.py            # Gemelo digital del almacén
│   ├── maestro.py           # Maestro de artículos e inventario
│   └── escaner.py           # Escáner móvil QR
│
└── (solo local)
    └── serial_rfid_bridge.py # Bridge ESP32 USB → Archivo (solo PC)
```

## 🚀 Despliegue

### **Streamlit Cloud:**
1. Configurar Secrets en Settings:
   ```toml
   FIREBASE_URL = "https://tu-proyecto.firebaseio.com/maestro_articulos.json"
   UIDS_AUTORIZADOS = "06:7F:04:07,92:D1:10:06"
   PASSWORD_ACCESO = "1234567890"
   PASSWORD_ADMIN = "1020304050"
   ```

2. Push a GitHub (archivos necesarios):
   - app.py
   - config.py
   - firebase.py
   - logica.py
   - requirements.txt
   - ui/login.py
   - ui/gemelo.py
   - ui/maestro.py
   - ui/escaner.py

### **Local (con ESP32):**
1. Conectar ESP32 por USB
2. Ejecutar: `python serial_rfid_bridge.py`
3. En otra terminal: `streamlit run app.py`

## 📦 Características

- ✅ Login RFID + contraseña
- ✅ Gemelo digital 3D del almacén
- ✅ Asignación automática de ubicaciones por peso/volumen
- ✅ Escáner QR móvil
- ✅ Pick-to-light (MQTT, opcional)
- ✅ Alertas de reorden
- ✅ Historial de movimientos

## 🔧 Configuración ESP32

El ESP32 envía UIDs a Firebase via HTTP:
```
Endpoint: /rfid_pendiente.json
Formato: {"uid": "06:7F:04:07", "ts": 1776800500}
```

## 📱 Modos de Uso

- **Escritorio:** Gemelo Digital + Maestro de Artículos
- **Móvil:** Escáner QR + Alta de Material

---

**Versión:** 3.0  
**Última actualización:** Abril 2026
