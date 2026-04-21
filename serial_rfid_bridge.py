"""
serial_rfid_bridge.py
Lee UIDs del ESP32 por Serial y los guarda en archivo para Streamlit
"""
import serial
import serial.tools.list_ports
import time
import json
import os
from datetime import datetime
import paho.mqtt.client as mqtt
import ssl

# CONFIGURACIÓN
BAUDRATE = 115200
ARCHIVO_UID = "rfid_uid.json"

# MQTT Configuration
MQTT_ENABLED = True  # Cambiar a False para desactivar MQTT
MQTT_HOST = "0915b3e64d01444da73c24d109538a81.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "logistica123"
MQTT_PASS = "Logistica1"
MQTT_TOPIC_RFID = "almacen/rfid"

# Obtener ruta completa
RUTA_COMPLETA = os.path.abspath(ARCHIVO_UID)

print("╔════════════════════════════════════╗")
print("║   UMAD WMS - RFID Bridge           ║")
print("║   Serial → Archivo + MQTT          ║")
print("╚════════════════════════════════════╝\n")
print(f"Carpeta de trabajo: {os.getcwd()}")
print(f"Ruta completa del archivo: {RUTA_COMPLETA}")

# ─────────────────────────────────────────
# MQTT CLIENT
# ─────────────────────────────────────────
mqtt_client = None

def setup_mqtt():
    """Configura el cliente MQTT"""
    if not MQTT_ENABLED:
        print("\n[MQTT] Deshabilitado en configuración")
        return None
    
    try:
        print("\n[MQTT] Conectando a HiveMQ Cloud...")
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        client.username_pw_set(MQTT_USER, MQTT_PASS)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)
        
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()
        
        print(f"[MQTT] ✓ Conectado a {MQTT_HOST}")
        print(f"[MQTT] ✓ Publicará UIDs en topic: {MQTT_TOPIC_RFID}")
        return client
    except Exception as e:
        print(f"[MQTT] ✗ Error al conectar: {e}")
        print(f"[MQTT] Continuará solo con archivo local")
        return None

def publicar_uid_mqtt(uid):
    """Publica el UID por MQTT"""
    global mqtt_client
    
    if not mqtt_client:
        return False
    
    try:
        result = mqtt_client.publish(MQTT_TOPIC_RFID, uid)
        if result.rc == 0:
            print(f"[MQTT] ✓ UID publicado: {uid}")
            return True
        else:
            print(f"[MQTT] ✗ Error al publicar (rc={result.rc})")
            return False
    except Exception as e:
        print(f"[MQTT] ✗ Error: {e}")
        return False

# ─────────────────────────────────────────
# DETECCIÓN AUTOMÁTICA DE PUERTO
# ─────────────────────────────────────────
def detectar_puerto():
    """Detecta automáticamente el puerto del ESP32"""
    print("Buscando puerto serial del ESP32...")
    puertos = list(serial.tools.list_ports.comports())
    
    if not puertos:
        print("✗ No se encontraron puertos seriales")
        print("\nVerifica:")
        print("  1. El ESP32 está conectado por USB")
        print("  2. Los drivers están instalados")
        print("  3. El cable USB funciona (algunos solo cargan)")
        return None
    
    print(f"\nPuertos disponibles:")
    for i, puerto in enumerate(puertos, 1):
        print(f"  {i}. {puerto.device} - {puerto.description}")
    
    # Buscar automáticamente puertos comunes de ESP32
    for puerto in puertos:
        desc = puerto.description.lower()
        # ESP32 común: CP210x, CH340, FTDI
        if any(x in desc for x in ['cp210', 'ch340', 'uart', 'usb-serial', 'ftdi']):
            print(f"\n✓ ESP32 detectado en: {puerto.device}")
            return puerto.device
    
    # Si no se detectó automáticamente, preguntar al usuario
    print("\n⚠ No se detectó ESP32 automáticamente")
    print("Selecciona el puerto manualmente:")
    
    while True:
        try:
            seleccion = input(f"Ingresa el número (1-{len(puertos)}) o 'q' para salir: ").strip()
            
            if seleccion.lower() == 'q':
                return None
            
            idx = int(seleccion) - 1
            if 0 <= idx < len(puertos):
                puerto_seleccionado = puertos[idx].device
                print(f"✓ Puerto seleccionado: {puerto_seleccionado}")
                return puerto_seleccionado
            else:
                print(f"✗ Número inválido. Debe ser entre 1 y {len(puertos)}")
        except ValueError:
            print("✗ Entrada inválida. Ingresa un número o 'q'")

PUERTO_SERIAL = detectar_puerto()

if not PUERTO_SERIAL:
    print("\n✗ No se pudo conectar. Cerrando...")
    input("Presiona Enter para salir...")
    exit(1)

# Configurar MQTT
mqtt_client = setup_mqtt()

print(f"\n{'='*40}")
print("CONFIGURACIÓN:")
print(f"  Puerto Serial: {PUERTO_SERIAL}")
print(f"  Archivo Local: {ARCHIVO_UID}")
print(f"  MQTT: {'✓ Habilitado' if mqtt_client else '✗ Deshabilitado'}")
print(f"{'='*40}\n")

try:
    # Conectar al puerto serial
    print(f"Conectando a {PUERTO_SERIAL} @ {BAUDRATE} baudios...")
    ser = serial.Serial(PUERTO_SERIAL, BAUDRATE, timeout=1)
    time.sleep(2)  # Esperar a que el ESP32 se inicialice
    
    print(f"✓ Conectado a {PUERTO_SERIAL}")
    print(f"\n{'='*40}")
    print("Esperando tarjetas RFID...")
    print(f"{'='*40}\n")
    
    while True:
        if ser.in_waiting > 0:
            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            
            # Buscar líneas que empiecen con RFID_UID:
            if linea.startswith("RFID_UID:"):
                uid = linea.replace("RFID_UID:", "").strip()
                
                print(f"\n╔{'═'*38}╗")
                print(f"║  TARJETA DETECTADA                   ║")
                print(f"╚{'═'*38}╝")
                print(f"[{datetime.now().strftime('%H:%M:%S')}] UID: {uid}")
                
                # 1. Guardar en archivo local
                data = {
                    "uid": uid,
                    "timestamp": time.time()
                }
                
                with open(ARCHIVO_UID, 'w') as f:
                    json.dump(data, f)
                
                # Verificar que se guardó
                if os.path.exists(ARCHIVO_UID):
                    tamaño = os.path.getsize(ARCHIVO_UID)
                    print(f"[Archivo] ✓ Guardado localmente ({tamaño} bytes)")
                else:
                    print(f"[Archivo] ✗ Error al guardar")
                
                # 2. Publicar por MQTT
                if mqtt_client:
                    publicar_uid_mqtt(uid)
                
                print(f"{'─'*40}\n")
            else:
                # Imprimir otros mensajes del ESP32
                if linea and not linea.startswith('['):
                    print(f"[ESP32] {linea}")
        
        time.sleep(0.1)

except serial.SerialException as e:
    print(f"\n✗ Error de conexión serial: {e}")
    print("\nPosibles soluciones:")
    print("  1. Verifica que el ESP32 esté conectado")
    print("  2. Cierra Arduino IDE (no puede haber dos programas usando el puerto)")
    print("  3. Verifica el nombre del puerto:")
    print("     - Windows: Abre 'Administrador de dispositivos' → Puertos COM")
    print("     - Mac: Ejecuta: ls /dev/cu.*")
    print("     - Linux: Ejecuta: ls /dev/ttyUSB*")

except KeyboardInterrupt:
    print("\n\n✓ Bridge detenido por el usuario")
    ser.close()

except Exception as e:
    print(f"\n✗ Error inesperado: {e}")
