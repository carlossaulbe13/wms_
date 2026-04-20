"""
serial_rfid_bridge.py
Lee UIDs del ESP32 por Serial y los guarda en archivo para Streamlit
"""
import serial
import time
import json
from datetime import datetime

# CONFIGURACIÓN
PUERTO_SERIAL = "COM3"  # Windows: COM3, COM4, etc. | Mac/Linux: /dev/ttyUSB0, /dev/cu.usbserial, etc.
BAUDRATE = 115200
ARCHIVO_UID = "rfid_uid.json"

print("╔════════════════════════════════════╗")
print("║   UMAD WMS - RFID Bridge           ║")
print("╚════════════════════════════════════╝\n")

try:
    # Conectar al puerto serial
    print(f"Conectando a {PUERTO_SERIAL} @ {BAUDRATE} baudios...")
    ser = serial.Serial(PUERTO_SERIAL, BAUDRATE, timeout=1)
    time.sleep(2)  # Esperar a que el ESP32 se inicialice
    
    print(f"✓ Conectado a {PUERTO_SERIAL}")
    print(f"✓ Guardando UIDs en: {ARCHIVO_UID}")
    print(f"\n{'='*40}")
    print("Esperando tarjetas RFID...")
    print(f"{'='*40}\n")
    
    while True:
        if ser.in_waiting > 0:
            linea = ser.readline().decode('utf-8', errors='ignore').strip()
            
            # Buscar líneas que empiecen con RFID_UID:
            if linea.startswith("RFID_UID:"):
                uid = linea.replace("RFID_UID:", "").strip()
                
                # Guardar UID con timestamp
                data = {
                    "uid": uid,
                    "timestamp": time.time()
                }
                
                with open(ARCHIVO_UID, 'w') as f:
                    json.dump(data, f)
                
                print(f"[{datetime.now().strftime('%H:%M:%S')}] UID detectado: {uid}")
                print(f"  → Guardado en {ARCHIVO_UID}\n")
            else:
                # Imprimir otros mensajes del ESP32
                if linea:
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
