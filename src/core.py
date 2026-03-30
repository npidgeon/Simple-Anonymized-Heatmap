"""
core.py

Contains the core geographic logic for generating boundaries and jittering coordinates
to apply anonymity to location data.
"""

import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import numpy as np


def create_us_boundary(shapefile_path, include_territories=True, buffer_meters=5000):
    """
    Loads a US nation shapefile and returns a polygon/multipolygon for the US
    with an optional buffer applied to the boundary.
    
    Args:
        shapefile_path (str): Path to the .shp file.
        include_territories (bool): If True, retains AK, HI, PR, etc. If False, only contiguous US.
        buffer_meters (int): Adds a margin to the boundary to allow offshore points.
    """
    us_gdf = gpd.read_file(shapefile_path)
    all_us_parts = us_gdf.iloc[0].geometry

    # Optional: Isolate contiguous US by finding the largest polygon
    if not include_territories:
        boundary_geom = max(all_us_parts.geoms, key=lambda p: p.area)
    else:
        # buffer(0) fixes invalid geometries that sometimes occur in shapefiles
        boundary_geom = all_us_parts.buffer(0)

    # Apply a buffer to the boundary in degrees
    earth_radius = 6378137 
    buffer_degrees = buffer_meters / earth_radius * (180 / np.pi)
    buffered_polygon = boundary_geom.buffer(buffer_degrees)

    return buffered_polygon


def fast_jitter_with_boundary(df, lat_col, lon_col, offset_meters, boundary):
    """
    Applies a random offset to coordinates using a fast, vectorized approach,
    ensuring they stay within the provided geographic boundary.
    """
    earth_radius = 6378137
    random_distances = np.sqrt(np.random.uniform(0, 1, size=len(df))) * offset_meters
    random_angles = np.random.uniform(0, 2 * np.pi, size=len(df))

    lat_offset_m = random_distances * np.sin(random_angles)
    lon_offset_m = random_distances * np.cos(random_angles)

    lat_offset_deg = lat_offset_m / earth_radius * (180 / np.pi)
    lon_offset_deg = lon_offset_m / (earth_radius * np.cos(np.radians(df[lat_col]))) * (180 / np.pi)

    jittered_df = pd.DataFrame({
        'lat_jittered': df[lat_col] + lat_offset_deg,
        'lon_jittered': df[lon_col] + lon_offset_deg,
        'original_index': df.index 
    })
    
    gdf_jittered = gpd.GeoDataFrame(
        jittered_df, 
        geometry=gpd.points_from_xy(jittered_df.lon_jittered, jittered_df.lat_jittered),
        crs="EPSG:4326"
    )
    
    boundary_gdf = gpd.GeoDataFrame([{'geometry': boundary}], crs="EPSG:4326")

    valid_points = gpd.sjoin(gdf_jittered, boundary_gdf, how="inner", predicate="within")
    
    invalid_indices = jittered_df[~jittered_df['original_index'].isin(valid_points['original_index'])].original_index
    
    if not invalid_indices.empty:
        fixed_points_df = jitter_coordinates_with_boundary(df.loc[invalid_indices], lat_col, lon_col, offset_meters, boundary)
        final_df = pd.concat([
            valid_points[['lat_jittered', 'lon_jittered']],
            fixed_points_df
        ], ignore_index=True)
    else:
        final_df = valid_points[['lat_jittered', 'lon_jittered']]

    return final_df


def jitter_coordinates_with_boundary(df, lat_col, lon_col, offset_meters, boundary):
    """
    Slower, iterative method used to re-jitter points that failed the vectorized boundary check.
    """
    earth_radius = 6378137
    jittered_points = []

    for index, row in df.iterrows():
        original_lat = row[lat_col]
        original_lon = row[lon_col]
        
        while True:
            random_distance = np.sqrt(np.random.uniform(0, 1)) * offset_meters
            random_angle = np.random.uniform(0, 2 * np.pi)

            lat_offset_m = random_distance * np.sin(random_angle)
            lon_offset_m = random_distance * np.cos(random_angle)
            
            lat_offset_deg = lat_offset_m / earth_radius * (180 / np.pi)
            lon_offset_deg = lon_offset_m / (earth_radius * np.cos(np.radians(original_lat))) * (180 / np.pi)

            new_lat = original_lat + lat_offset_deg
            new_lon = original_lon + lon_offset_deg
            new_point = Point(new_lon, new_lat) 

            if boundary.contains(new_point):
                jittered_points.append({'lat_jittered': new_lat, 'lon_jittered': new_lon})
                break
                
    return pd.DataFrame(jittered_points)
