import streamlit as st
import paho.mqtt.client as mqtt
import json
import requests
import pandas as pd
import qrcode
import plotly.graph_objects as go
import time
from datetime import datetime

# --- CONFIGURACIÓN DE NUBE Y MQTT (DATOS ORIGINALES) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"
MQTT_HOST = "03109e9f1c90423e81ffa63071592873.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USER = "saul_mqtt"
MQTT_PASS = "135700/Saul"
TOPIC_PUB = "almacen/escaneo"

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="UMAD Warehouse System", layout="wide")

# --- FUNCIONES DE BASE DE DATOS ---
def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        return res.json() if res.status_code == 200 and res.json() else {}
    except:
        return {}

def guardar_db(db):
    requests.put(FIREBASE_URL, json=db)

# --- LÓGICA DE BÚSQUEDA DE UBICACIÓN (NUEVAS DIMENSIONES) ---
def obtener_espacio_disponible(db, peso_nuevo, tipo_contenedor):
    # Definición de estructura basada en el layout 13x37
    filas = ["A", "B", "C", "D"]
    secciones = range(1, 6) # 5 secciones de 3 metros
    niveles = range(1, 4)   # 3 niveles de altura
    posiciones = range(1, 4) # 3 posiciones por viga de 3m
    LIMITE_PESO_NIVEL = 2100.0

    # Lógica para Tinas/Tambos (Zona Sobredimensiones 7-17m)
    if tipo_contenedor in ["Tina LAMTEC", "Tambo 200L"]:
        # Aquí buscaría en una lista de slots de piso (simplificado por ahora)
        return "PISO", "ZONA_NARANJA", 0, 0

    # Lógica para Racks (Pintura/KLT)
    for f in filas:
        for s in secciones:
            for n in niveles:
                # Calcular peso actual en este nivel (viga de 3m)
                peso_actual = sum([float(item.get('peso', 0)) for item in db.values() 
                                  if item.get('fila') == f and item.get('seccion') == s and item.get('nivel') == n])
                
                if (peso_actual + peso_nuevo) <= LIMITE_PESO_NIVEL:
                    for p in posiciones:
                        # Verificar si la posición exacta está libre
                        ocupado = any(item for item in db.values() 
                                     if item.get('fila') == f and item.get('seccion') == s 
                                     and item.get('nivel') == n and item.get('posicion') == p)
                        if not ocupado:
                            return f, s, n, p
    return None

# --- MAPA VISUAL (LAYOUT LIMPIO) ---
def dibujar_layout():
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=37, line=dict(color="Black", width=3)) # Nave
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=7, fillcolor="LightSteelBlue", opacity=0.3, line_width=0) # Recepción
    fig.add_shape(type="rect", x0=0, y0=7, x1=13, y1=17, fillcolor="NavajoWhite", opacity=0.3, line_width=0) # Sobredimensiones
    fig.add_shape(type="rect", x0=0, y0=33, x1=13, y1=37, fillcolor="PaleGreen", opacity=0.3, line_width=0) # Retorno
    
    # Racks (Bloques consolidados por ahora)
    racks_x = [(0, 1.05), (5.05, 7.15), (11.15, 12.2)]
    for rx in racks_x:
        fig.add_shape(type="rect", x0=rx[0], y0=17, x1=rx[1], y1=32.5, fillcolor="DarkSlateBlue")

    fig.update_layout(xaxis=dict(range=[-1, 14], showgrid=False), yaxis=dict(range=[-1, 38], showgrid=False),
                      plot_bgcolor='white', width=450, height=800, showlegend=False)
    return fig

# --- INTERFAZ ---
st.sidebar.title("Navegación")
menu = st.sidebar.radio("Ir a:", ["Monitoreo y Ubicación", "Registro de Entrada", "Salida a Producción"])

if menu == "Monitoreo y Ubicación":
    st.header("📍 Monitoreo en Tiempo Real")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.plotly_chart(dibujar_layout())
    with col2:
        st.subheader("Inventario Activo")
        db = cargar_db()
        if db:
            df = pd.DataFrame.from_dict(db, orient='index')
            st.dataframe(df[['nombre', 'fila', 'seccion', 'nivel', 'peso']])
        else:
            st.info("Almacén vacío.")

elif menu == "Registro de Entrada":
    st.header("📥 Entrada de Material")
    with st.form("registro_entrada"):
        nombre = st.text_input("Nombre del Material (ej. Pintura Blanca)")
        tipo = st.selectbox("Tipo de Contenedor", ["Caja KLT", "Pallet Estándar", "Tina LAMTEC", "Tambo 200L"])
        peso = st.number_input("Peso Total (kg)", min_value=1.0)
        submit = st.form_submit_button("Asignar Ubicación Automática")

        if submit:
            db = cargar_db()
            resultado = obtener_espacio_disponible(db, peso, tipo)
            
            if resultado:
                fila, seccion, nivel, pos = resultado
                new_id = f"ID-{int(time.time())}"
                db[new_id] = {
                    "nombre": nombre, "tipo": tipo, "peso": peso,
                    "fila": fila, "seccion": seccion, "nivel": nivel, "posicion": pos,
                    "fecha": str(datetime.now())
                }
                guardar_db(db)
                st.success(f"Asignado a: FILA {fila}, SECCIÓN {seccion}, NIVEL {nivel}, POSICIÓN {pos}")
                st.image(qrcode.make(new_id).get_image(), width=200)
            else:
                st.error("No hay espacio disponible para esta carga.")
