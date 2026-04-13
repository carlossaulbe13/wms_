import streamlit as st
import paho.mqtt.client as mqtt
import requests
import pandas as pd
import plotly.graph_objects as go
import time

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="UMAD Warehouse System", layout="wide")

# --- CONFIGURACIÓN DE NUBE (FIREBASE) ---
FIREBASE_URL = "https://umad-wms-default-rtdb.firebaseio.com/maestro_articulos.json"

def cargar_db():
    try:
        res = requests.get(FIREBASE_URL)
        if res.status_code == 200 and res.json() is not None:
            return res.json()
    except:
        pass
    return {}

# --- LÓGICA DE VISUALIZACIÓN DEL LAYOUT ---
def dibujar_layout_interactivo():
    fig = go.Figure()

    # 1. Contorno de la Nave (13m x 37m)
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=37, line=dict(color="Black", width=4))

    # 2. Zonificación Longitudinal (Eje Y)
    # Recepción (0-7m)
    fig.add_shape(type="rect", x0=0, y0=0, x1=13, y1=7, fillcolor="SkyBlue", opacity=0.3, layer="below")
    
    # Sobredimensiones (7-17m)
    fig.add_shape(type="rect", x0=0, y0=7, x1=13, y1=17, fillcolor="Orange", opacity=0.2, layer="below")
    
    # Zona de Racks (17-33m)
    fig.add_shape(type="rect", x0=0, y0=17, x1=13, y1=33, fillcolor="LightGrey", opacity=0.1, layer="below")
    
    # Maniobra de Retorno (33-37m)
    fig.add_shape(type="rect", x0=0, y0=33, x1=13, y1=37, fillcolor="LimeGreen", opacity=0.2, layer="below")

    # 3. Dibujo de Racks (Basado en vigas de 3m y marcos de 1.05m)
    # Rack Izquierdo
    fig.add_shape(type="rect", x0=0, y0=17, x1=1.05, y1=32.5, fillcolor="RoyalBlue", line=dict(color="DarkBlue"))
    
    # Rack Doble Central (2.10m de profundidad total)
    fig.add_shape(type="rect", x0=5.05, y0=17, x1=7.15, y1=32.5, fillcolor="RoyalBlue", line=dict(color="DarkBlue"))
    
    # Rack Derecho
    fig.add_shape(type="rect", x0=11.15, y0=17, x1=12.2, y1=32.5, fillcolor="RoyalBlue", line=dict(color="DarkBlue"))

    # Anotaciones de Zonas
    fig.add_annotation(x=6.5, y=3.5, text="RECEPCIÓN", showarrow=False, font=dict(size=14, color="DarkBlue"))
    fig.add_annotation(x=6.5, y=12, text="SOBREDIMENSIONES (TINAS/TAMBOS)", showarrow=False, font=dict(size=14, color="DarkOrange"))
    fig.add_annotation(x=6.5, y=35, text="MANIOBRA DE RETORNO", showarrow=False, font=dict(size=14, color="DarkGreen"))

    fig.update_layout(
        title="MAPA OPERATIVO DEL ALMACÉN (13m x 37m)",
        xaxis=dict(range=[-1, 14], title="Frente (m)", dtick=1),
        yaxis=dict(range=[-1, 38], title="Largo (m)", dtick=5),
        width=450,
        height=800,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False
    )
    return fig

# --- INTERFAZ PRINCIPAL ---
st.title("🛡️ UMAD Warehouse System")
st.sidebar.header("Panel de Control")
menu = st.sidebar.radio("Navegación", ["Monitoreo y Ubicación", "Registro de Entrada", "Salida a Producción"])

if menu == "Monitoreo y Ubicación":
    st.header("📍 Estado Actual del Almacén")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Mapa de Planta")
        mapa = dibujar_layout_interactivo()
        st.plotly_chart(mapa, use_container_width=True)
    
    with col2:
        st.subheader("Leyenda y Detalles")
        st.info("""
        **Guía de Colores:**
        - 🟦 **Azul:** Racks Selectivos (Vigas 3m).
        - 🟧 **Naranja:** Zona de Piso para Tinas Pesadas.
        - 🟩 **Verde:** Área de Retorno (Circulación).
        - 🟦 **Cian:** Área de Recepción.
        """)
        
        db = cargar_db()
        if db:
            df = pd.DataFrame.from_dict(db, orient='index')
            st.write("Últimos movimientos registrados:")
            st.dataframe(df[['nombre', 'rack', 'estado']].tail(5))
        else:
            st.warning("No hay datos en el inventario.")

elif menu == "Registro de Entrada":
    st.subheader("📥 Ingreso de Material de Proveedor")
    # Aquí irá tu lógica de formulario de registro...
    st.write("Formulario de entrada en desarrollo conforme al nuevo proceso...")

elif menu == "Salida a Producción":
    st.subheader("📤 Despacho de Material")
    # Aquí irá tu lógica de salida...
    st.write("Módulo de picking en desarrollo...")
