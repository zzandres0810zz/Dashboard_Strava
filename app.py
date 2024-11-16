import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
import os
from dotenv import load_dotenv
import json

# Configuración de la página
st.set_page_config(layout="wide")

# Título de la aplicación
st.title('Dashboard Strava')

def cargar_datos_desde_api():
    try:
        # Cargar variables del archivo .env
        load_dotenv()
        
        # Variables de autenticación
        client_id = os.getenv('STRAVA_CLIENT_ID')
        client_secret = os.getenv('STRAVA_CLIENT_SECRET')
        refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
        
        # Obtener access token
        response = requests.post(
            'https://www.strava.com/oauth/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token
            },
            timeout=10
        )
        
        access_token = response.json().get('access_token')
        if not access_token:
            st.error("No se pudo obtener el access token")
            return None
            
        # Obtener actividades
        headers = {'Authorization': f'Bearer {access_token}'}
        url = 'https://www.strava.com/api/v3/athlete/activities'
        
        actividades = []
        page = 1
        while True:
            response = requests.get(
                url, 
                headers=headers, 
                params={'per_page': 200, 'page': page},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                actividades.extend(data)
                page += 1
            else:
                break
        
        # Filtrar actividades de tipo Run
        actividades_run = [act for act in actividades if act['type'] == 'Run']
        
        # Crear DataFrame
        data = []
        for actividad in actividades_run:
            distancia_km = actividad['distance'] / 1000
            tiempo_min = actividad['moving_time'] / 60
            pace_promedio = tiempo_min / distancia_km if distancia_km > 0 else None
            
            data.append({
                'Fecha': datetime.strptime(actividad['start_date'][:10], "%Y-%m-%d"),
                'Distancia (km)': round(distancia_km, 2),
                'Tiempo (min)': round(tiempo_min, 2),
                'Pace promedio (min/km)': round(pace_promedio, 2) if pace_promedio else None,
                'Pulsaciones promedio': actividad.get('average_heartrate'),
                'Cadencia promedio': actividad.get('average_cadence')
            })
        
        df = pd.DataFrame(data)
        
        # Guardar datos en cache
        df.to_csv('cached_activities.csv', index=False)
        return df
        
    except Exception as e:
        st.error(f"Error al cargar datos desde API: {str(e)}")
        return None

def cargar_datos_desde_cache():
    try:
        if os.path.exists('cached_activities.csv'):
            df = pd.read_csv('cached_activities.csv')
            df['Fecha'] = pd.to_datetime(df['Fecha'])
            return df
        return None
    except Exception as e:
        st.error(f"Error al cargar datos desde cache: {str(e)}")
        return None

def crear_grafica(df, y_column, title, y_label, color):
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df['Fecha'],
        y=df[y_column],
        marker_color=color,
        name=y_label
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title='Fecha',
        yaxis_title=y_label,
        height=300,
        margin=dict(l=50, r=50, t=50, b=50),
        showlegend=False,
        plot_bgcolor='white',
        bargap=0.2
    )
    
    # Agregar una línea de tendencia
    fig.add_trace(go.Scatter(
        x=df['Fecha'],
        y=df[y_column].rolling(window=3).mean(),
        mode='lines',
        line=dict(color='rgba(0,0,0,0.5)', width=2),
        name='Tendencia'
    ))
    
    return fig

def agregar_resample(df, periodo):
    """
    Agrupa los datos según el período seleccionado
    """
    mapping = {
        'Por actividad': None,
        'Diario': 'D',
        'Semanal': 'W-MON',
        'Mensual': 'M',
        'Trimestral': 'Q',
        'Anual': 'Y'
    }
    
    if periodo == 'Por actividad':
        return df
    
    # Agrupar datos según el período
    df_resampled = df.set_index('Fecha').resample(mapping[periodo]).agg({
        'Distancia (km)': 'sum',
        'Tiempo (min)': 'sum',
        'Pulsaciones promedio': 'mean',
        'Cadencia promedio': 'mean'
    }).reset_index()
    
    # Recalcular el pace promedio
    df_resampled['Pace promedio (min/km)'] = df_resampled['Tiempo (min)'] / df_resampled['Distancia (km)']
    
    return df_resampled

# Main
def main():
    # Agregar botón para recargar datos
    if st.button('Recargar datos desde Strava'):
        df = cargar_datos_desde_api()
    else:
        # Intentar cargar desde cache primero
        df = cargar_datos_desde_cache()
        if df is None:
            df = cargar_datos_desde_api()
    
    if df is None:
        st.error("No se pudieron cargar los datos. Por favor, verifica tu conexión a internet y las credenciales de Strava.")
        return
    
    # Mostrar información básica
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"Total de actividades: {len(df)}")
    with col2:
        st.write(f"Rango de fechas: {df['Fecha'].min().date()} a {df['Fecha'].max().date()}")
    
    # Filtros de fecha
    col1, col2 = st.columns(2)
    with col1:
        fecha_inicio = st.date_input(
            "Fecha inicial",
            min(df['Fecha']).date()
        )
    with col2:
        fecha_fin = st.date_input(
            "Fecha final",
            max(df['Fecha']).date()
        )
    
    # Filtrar datos según el rango de fechas
    mask = (df['Fecha'].dt.date >= fecha_inicio) & (df['Fecha'].dt.date <= fecha_fin)
    df_filtrado = df.loc[mask]
    
    # Agregar selector de período
    periodo = st.selectbox(
        'Seleccionar período de agrupación',
        ['Por actividad', 'Diario', 'Semanal', 'Mensual', 'Trimestral', 'Anual']
    )
    
    # Agrupar datos según el período seleccionado
    df_filtrado = agregar_resample(df_filtrado, periodo)
    
    # Crear gráficas con diferentes colores
    metricas = [
        ('Distancia (km)', 'Distancia por Actividad', 'Distancia (km)', '#FF4B4B'),
        ('Tiempo (min)', 'Tiempo por Actividad', 'Tiempo (minutos)', '#1F77B4'),
        ('Pace promedio (min/km)', 'Pace Promedio por Actividad', 'Pace (min/km)', '#2CA02C'),
        ('Pulsaciones promedio', 'Pulsaciones Promedio por Actividad', 'BPM', '#FF7F0E'),
        ('Cadencia promedio', 'Cadencia Promedio por Actividad', 'SPM', '#9467BD')
    ]
    
    # Mostrar todas las gráficas
    for col, titulo, y_label, color in metricas:
        fig = crear_grafica(df_filtrado, col, titulo, y_label, color)
        st.plotly_chart(fig, use_container_width=True)

    # Mostrar estadísticas resumen
    st.subheader("Estadísticas del período seleccionado")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(
            "Distancia total", 
            f"{df_filtrado['Distancia (km)'].sum():.2f} km",
            f"{df_filtrado['Distancia (km)'].mean():.2f} km/actividad"
        )
    
    with col2:
        total_tiempo = df_filtrado['Tiempo (min)'].sum()
        st.metric(
            "Tiempo total", 
            f"{total_tiempo/60:.1f} horas",
            f"{df_filtrado['Tiempo (min)'].mean():.0f} min/actividad"
        )
    
    with col3:
        st.metric(
            "Pace promedio", 
            f"{df_filtrado['Pace promedio (min/km)'].mean():.2f} min/km",
            f"±{df_filtrado['Pace promedio (min/km)'].std():.2f} min/km"
        )

if __name__ == "__main__":
    main()