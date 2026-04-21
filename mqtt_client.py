"""
diagnostico_mqtt.py - Script para diagnosticar conexión MQTT y RFID
"""
import paho.mqtt.client as mqtt
import ssl
import time

# Configuración MQTT
MQTT_HOST = "0915b3e64d01444da73c24d109538a81.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "logistica123"
MQTT_PASS = "Logistica1"
TOPIC_RFID = "almacen/rfid"

print("╔════════════════════════════════════╗")
print("║   DIAGNÓSTICO MQTT + RFID          ║")
print("╚════════════════════════════════════╝\n")

def on_connect(client, userdata, flags, rc):
    """Callback cuando se conecta al broker"""
    if rc == 0:
        print("✅ [MQTT] CONECTADO al broker HiveMQ")
        print(f"   Host: {MQTT_HOST}")
        print(f"   Port: {MQTT_PORT}\n")
        
        # Suscribirse al topic RFID
        client.subscribe(TOPIC_RFID)
        print(f"✅ [MQTT] Suscrito al topic: {TOPIC_RFID}\n")
        print("📡 Esperando mensajes RFID...")
        print("   (Pasa tu tarjeta RFID ahora)\n")
    else:
        print(f"❌ [MQTT] ERROR al conectar. Código: {rc}")
        print(f"   0 = Success")
        print(f"   1 = Protocol version error")
        print(f"   2 = Client ID error")
        print(f"   3 = Server unavailable")
        print(f"   4 = Bad username/password")
        print(f"   5 = Not authorized\n")

def on_message(client, userdata, msg):
    """Callback cuando llega un mensaje"""
    payload = msg.payload.decode('utf-8')
    print(f"\n╔══════════════════════════════════╗")
    print(f"║  MENSAJE RECIBIDO                ║")
    print(f"╚══════════════════════════════════╝")
    print(f"Topic:   {msg.topic}")
    print(f"Payload: {payload}")
    print(f"Hora:    {time.strftime('%H:%M:%S')}")
    print(f"════════════════════════════════════\n")

def on_disconnect(client, userdata, rc):
    """Callback cuando se desconecta"""
    if rc != 0:
        print(f"\n⚠️ [MQTT] Desconexión inesperada. Código: {rc}")
        print("   Intentando reconectar...\n")

# Crear cliente MQTT
try:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="diagnostico_umad")
except:
    client = mqtt.Client(client_id="diagnostico_umad")

# Configurar callbacks
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

# Configurar TLS
client.username_pw_set(MQTT_USER, MQTT_PASS)
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.tls_insecure_set(True)

# Conectar
print("🔌 Conectando al broker MQTT...")
print(f"   Host: {MQTT_HOST}")
print(f"   Port: {MQTT_PORT}")
print(f"   User: {MQTT_USER}\n")

try:
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()
    
    # Mantener el script corriendo
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("Presiona Ctrl+C para salir")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    while True:
        time.sleep(1)
        
except KeyboardInterrupt:
    print("\n\n✅ Diagnóstico finalizado")
    client.loop_stop()
    client.disconnect()
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nPosibles causas:")
    print("  1. Credenciales incorrectas")
    print("  2. Host MQTT incorrecto")
    print("  3. Puerto bloqueado (firewall)")
    print("  4. Sin conexión a internet")
