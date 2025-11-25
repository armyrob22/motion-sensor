import streamlit as st
import psycopg2
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import numpy as np
import os
from sqlalchemy import create_engine

# Database configuration
DB_HOST = os.getenv('DB_HOST', '10.107.210.5')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_NAME = os.getenv('DB_NAME', 'motion_data')
DB_USER = os.getenv('DB_USER', 'armyrob')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'default_password')

# Page config
st.set_page_config(
    page_title="STM32 Vibration Monitor",
    page_icon="📊",
    layout="wide"
)

# Create SQLAlchemy connection string
DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

@st.cache_resource
def get_db_engine():
    """Create SQLAlchemy engine"""
    return create_engine(DATABASE_URL)

def fetch_data(query, params=None):
    """Fetch data from database"""
    conn = get_db_engine()
    df = pd.read_sql_query(query, conn, params=params)
    return df

def fetch_stats():
    """Get summary statistics"""
    query = """
        SELECT 
            COUNT(*) as total_samples,
            MIN(timestamp) as first_sample,
            MAX(timestamp) as last_sample,
            AVG(x_accel) as avg_x,
            AVG(y_accel) as avg_y,
            AVG(z_accel) as avg_z,
            STDDEV(x_accel) as std_x,
            STDDEV(y_accel) as std_y,
            STDDEV(z_accel) as std_z,
            MIN(x_accel) as min_x,
            MAX(x_accel) as max_x,
            MIN(y_accel) as min_y,
            MAX(y_accel) as max_y,
            MIN(z_accel) as min_z,
            MAX(z_accel) as max_z
        FROM vibration_data
    """
    return fetch_data(query)

def fetch_recent_data(limit=1000):
    """Fetch most recent samples"""
    query = f"""
        SELECT id, timestamp, x_accel, y_accel, z_accel, change_value
        FROM vibration_data
        ORDER BY id DESC
        LIMIT {limit}
    """
    df = fetch_data(query)
    return df.sort_values('id')  # Sort chronologically for plotting

def fetch_time_range_data(hours=24):
    """Fetch data from last N hours with smart downsampling"""
    
    # For large time ranges, downsample to every Nth sample
    if hours > 24:
        sample_interval = max(1, int(hours / 24))  # More hours = more downsampling
        query = f"""
            SELECT id, timestamp, x_accel, y_accel, z_accel, change_value
            FROM vibration_data
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours'
            AND id % {sample_interval} = 0
            ORDER BY id ASC
        """
    else:
        query = f"""
            SELECT id, timestamp, x_accel, y_accel, z_accel, change_value
            FROM vibration_data
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours'
            ORDER BY id ASC
        """
    return fetch_data(query, params=(hours,))

def main():
    st.title("🔧 STM32 Vibration Monitoring Dashboard")
    st.markdown("Real-time vibration monitoring using MPU6050 accelerometer")
    
    # Sidebar controls
    st.sidebar.header("Controls")
    
    view_mode = st.sidebar.radio(
        "View Mode",
        ["Recent Samples", "Time Range", "Statistics"]
    )
    
    if view_mode == "Recent Samples":
        sample_count = st.sidebar.slider("Number of samples", 100, 10000, 1000, 100)
        df = fetch_recent_data(sample_count)
        
    elif view_mode == "Time Range":
        hours = st.sidebar.slider("Hours of history", 1, 168, 24)
        df = fetch_time_range_data(hours)
        
    else:  # Statistics mode
        df = None
    
    # Auto-refresh toggle
    auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=False)
    if auto_refresh:
        st.rerun()
    
    # Display statistics cards
    st.header("📈 Summary Statistics")
    stats = fetch_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Samples", f"{stats['total_samples'].iloc[0]:,}")
    with col2:
        st.metric("Monitoring Since", 
                  stats['first_sample'].iloc[0].strftime("%Y-%m-%d %H:%M") if pd.notna(stats['first_sample'].iloc[0]) else "N/A")
    with col3:
        st.metric("Last Update", 
                  stats['last_sample'].iloc[0].strftime("%Y-%m-%d %H:%M") if pd.notna(stats['last_sample'].iloc[0]) else "N/A")
    with col4:
        if df is not None:
            st.metric("Samples Displayed", f"{len(df):,}")
    
    if view_mode == "Statistics":
        # Detailed statistics view
        st.header("📊 Detailed Statistics")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("X-Axis")
            st.metric("Average", f"{stats['avg_x'].iloc[0]:.4f}g")
            st.metric("Std Dev", f"{stats['std_x'].iloc[0]:.4f}g")
            st.metric("Range", f"{stats['min_x'].iloc[0]:.4f}g to {stats['max_x'].iloc[0]:.4f}g")
            
        with col2:
            st.subheader("Y-Axis")
            st.metric("Average", f"{stats['avg_y'].iloc[0]:.4f}g")
            st.metric("Std Dev", f"{stats['std_y'].iloc[0]:.4f}g")
            st.metric("Range", f"{stats['min_y'].iloc[0]:.4f}g to {stats['max_y'].iloc[0]:.4f}g")
            
        with col3:
            st.subheader("Z-Axis")
            st.metric("Average", f"{stats['avg_z'].iloc[0]:.4f}g")
            st.metric("Std Dev", f"{stats['std_z'].iloc[0]:.4f}g")
            st.metric("Range", f"{stats['min_z'].iloc[0]:.4f}g to {stats['max_z'].iloc[0]:.4f}g")
        
        return
    
    if df is None or len(df) == 0:
        st.warning("No data available")
        return
    
    # Time series visualization
    st.header("📉 Acceleration Time Series")
    
    # Create subplot with 3 axes
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        subplot_titles=('X-Axis Acceleration', 'Y-Axis Acceleration', 'Z-Axis Acceleration'),
        vertical_spacing=0.08
    )
    
    # X-axis
    fig.add_trace(
        go.Scatter(x=df['id'], y=df['x_accel'], name='X', line=dict(color='red', width=1)),
        row=1, col=1
    )
    
    # Y-axis
    fig.add_trace(
        go.Scatter(x=df['id'], y=df['y_accel'], name='Y', line=dict(color='green', width=1)),
        row=2, col=1
    )
    
    # Z-axis
    fig.add_trace(
        go.Scatter(x=df['id'], y=df['z_accel'], name='Z', line=dict(color='blue', width=1)),
        row=3, col=1
    )
    
    fig.update_xaxes(title_text="Sample ID", row=3, col=1)
    fig.update_yaxes(title_text="Acceleration (g)", row=1, col=1)
    fig.update_yaxes(title_text="Acceleration (g)", row=2, col=1)
    fig.update_yaxes(title_text="Acceleration (g)", row=3, col=1)
    
    fig.update_layout(height=800, showlegend=True)
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 3D magnitude visualization
    st.header("📊 Acceleration Magnitude")
    
    df['magnitude'] = np.sqrt(df['x_accel']**2 + df['y_accel']**2 + df['z_accel']**2)
    
    fig_mag = go.Figure()
    fig_mag.add_trace(go.Scatter(
        x=df['id'], 
        y=df['magnitude'],
        mode='lines',
        name='Magnitude',
        line=dict(color='purple', width=2)
    ))
    
    fig_mag.update_layout(
        title="Total Acceleration Magnitude",
        xaxis_title="Sample ID",
        yaxis_title="Magnitude (g)",
        height=400
    )
    
    st.plotly_chart(fig_mag, use_container_width=True)
    
    # Anomaly detection
    st.header("⚠️ Anomaly Detection")
    
    threshold = st.slider("Magnitude Threshold (g)", 0.5, 2.0, 1.2, 0.05)
    anomalies = df[df['magnitude'] > threshold]
    
    if len(anomalies) > 0:
        st.warning(f"Found {len(anomalies)} samples exceeding {threshold}g threshold")
        st.dataframe(anomalies[['id', 'timestamp', 'x_accel', 'y_accel', 'z_accel', 'magnitude']].head(20))
    else:
        st.success(f"No samples exceed {threshold}g threshold")
    
    # Raw data table
    with st.expander("📋 Raw Data (Latest 100 samples)"):
        st.dataframe(df.tail(100))

if __name__ == "__main__":
    main()