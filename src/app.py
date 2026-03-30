"""
app.py

Main Streamlit application for Simple-Anonymized-Heatmap.
Provides an interactive GUI to upload data, set privacy parameters,
and visualize the anonymized heatmap in real-time.
"""

import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
import geopandas as gpd
import os

from core import create_us_boundary, fast_jitter_with_boundary
from aws_utils import fetch_s3_csv

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Simple Anonymized Heatmap",
    page_icon="🗺️",
    layout="wide"
)

# Resolve standard paths independent of execution directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHAPEFILE_PATH = os.path.join(BASE_DIR, 'data', 'cb_2018_us_nation_5m.shp')


@st.cache_resource
def load_boundary(include_territories=True):
    """Loads and caches the US shapefile boundary."""
    try:
        return create_us_boundary(SHAPEFILE_PATH, include_territories=include_territories, buffer_meters=5000)
    except Exception as e:
        st.error(f"Error loading shapefile from {SHAPEFILE_PATH}. Details: {e}")
        return None

# --- UI LOGIC ---
st.title("🗺️ Simple Anonymized Heatmap")
st.markdown("Upload coordinate data to generate a privacy-preserving heatmap bound within the US.")

# Sidebar Controls
with st.sidebar:
    st.header("1. Data Source")
    data_source = st.radio("Choose input method:", ("Upload Local CSV", "Fetch from AWS S3"))
    
    df = None

    if data_source == "Upload Local CSV":
        uploaded_file = st.file_uploader("Upload your CSV file", type=['csv'])
        if uploaded_file is not None:
            df = pd.read_csv(uploaded_file)
            st.success(f"Loaded {len(df)} records.")
            
    elif data_source == "Fetch from AWS S3":
        st.info("Enter your AWS credentials below. They are not saved or stored.")
        aws_key = st.text_input("AWS Access Key ID", type="password")
        aws_secret = st.text_input("AWS Secret Access Key", type="password")
        bucket_name = st.text_input("S3 Bucket Name")
        file_key = st.text_input("CSV File Key (Path)")
        
        if st.button("Fetch from S3"):
            if all([aws_key, aws_secret, bucket_name, file_key]):
                with st.spinner("Connecting to AWS..."):
                    try:
                        df = fetch_s3_csv(aws_key, aws_secret, bucket_name, file_key)
                        st.session_state['s3_df'] = df
                        st.success(f"Successfully loaded {len(df)} rows from S3.")
                    except Exception as e:
                        st.error(f"AWS Error: {e}")
            else:
                st.warning("Please fill in all AWS fields.")

    # Retrieve from session state if using S3
    if data_source == "Fetch from AWS S3" and 's3_df' in st.session_state:
        df = st.session_state['s3_df']

    st.divider()

    st.header("2. Configuration")
    lat_col = st.text_input("Latitude Column Name", value="lat")
    lon_col = st.text_input("Longitude Column Name", value="long")
    
    radius = st.slider("Jitter Radius (Meters)", min_value=0, max_value=5000, value=500, step=50, 
                       help="Maximum distance a coordinate can be randomized to preserve anonymity.")
                       
    include_territories = st.checkbox("Include AK, HI & Territories", value=True)

    st.divider()
    generate_btn = st.button("Generate Heatmap", type="primary", use_container_width=True)


# --- MAIN LOGIC ---
if generate_btn:
    if df is not None:
        if lat_col not in df.columns or lon_col not in df.columns:
            st.error(f"Columns '{lat_col}' and/or '{lon_col}' not found in the dataset. Available columns: {list(df.columns)}")
        else:
            df = df.dropna(subset=[lat_col, lon_col])
            
            with st.spinner("Loading geographical boundaries..."):
                us_boundary = load_boundary(include_territories=include_territories)
            
            if us_boundary is not None:
                with st.spinner(f"Filtering and applying {radius}m jitter to coordinates..."):
                    # Pre-filter source data to find points within the boundary
                    source_gdf = gpd.GeoDataFrame(
                        df,
                        geometry=gpd.points_from_xy(df[lon_col], df[lat_col]),
                        crs="EPSG:4326"
                    )
                    boundary_gdf = gpd.GeoDataFrame([{'geometry': us_boundary}], crs="EPSG:4326")
                    
                    # Find points that started inside
                    us_members = gpd.sjoin(source_gdf, boundary_gdf, how="inner", predicate="within")
                    original_count = len(df)
                    filtered_count = len(us_members)

                    st.info(f"Loaded {original_count} total records. Kept {filtered_count} records located within the selected US boundary.")
                    
                    if filtered_count > 0:
                        anonymized_df = fast_jitter_with_boundary(
                            us_members.drop(columns=['index_right']),
                            lat_col,
                            lon_col,
                            radius,
                            us_boundary
                        )
                        
                        st.success("Anonymization complete. Rendering Map...")
                        
                        # --- RENDER MAP ---
                        map_center = [39.82, -98.57]
                        # Bounds approx. continental US. (if territories included, you can zoom out manually in the app)
                        map_bounds = [[24, -125], [50, -66]]

                        m = folium.Map(
                            location=map_center, 
                            zoom_start=4, 
                            tiles='CartoDB positron'
                        )
                        m.fit_bounds(map_bounds)
                        
                        heatmap_data = anonymized_df[['lat_jittered', 'lon_jittered']].values.tolist()
                        HeatMap(heatmap_data, radius=8, blur=5).add_to(m)

                        # Render folium in streamlit
                        st_folium(m, width=1200, height=700, returned_objects=[])
                        
                    else:
                        st.warning("No data points found within the US boundary.")
    else:
        st.warning("Please upload a CSV file or fetch one from S3 first.")
elif df is None:
    st.info("Awaiting data input from the sidebar...")
