import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from shapely.geometry import Polygon
import numpy as np
import folium
from folium.plugins import HeatMap
import os
import io
import boto3


# This program takes a CSV file with latitude and longitude coordinates as input,
# applies a random jitter to anonymize the coordinates, and generates a heatmap
# of the anonymized points, ensuring they remain within the continental US boundary.
# Heatmap is an HTML file that can be opened in a web browser.
# Last updated on July 28th, 2025

def create_continental_us_boundary(shapefile_path):
    
    # Loads a US nation shapefile and returns a polygon for the continental US
    # by finding the largest polygon by area.
    
    print("Loading US boundary shapefile...")
    us_gdf = gpd.read_file(shapefile_path)

    # The 'nation' file has one row. Get its geometry object.
    # This is a MultiPolygon containing the continental US, Alaska, Hawaii, etc.
    all_us_parts = us_gdf.iloc[0].geometry

    # Find the largest polygon within the MultiPolygon by checking the area of each part.
    # The largest part is the continental US.
    largest_polygon = max(all_us_parts.geoms, key=lambda p: p.area)
    
    print("Boundary for continental US created by isolating the largest polygon.")
    return largest_polygon

def fast_jitter_with_boundary(df, lat_col, lon_col, offset_meters, boundary):
    
    # Applies a random offset to coordinates using a fast, vectorized approach.
    
    print(f"Starting fast, vectorized jittering for {len(df)} records...")
    
    # Jitter ALL points at once (vectorized)
    earth_radius = 6378137
    random_distances = np.sqrt(np.random.uniform(0, 1, size=len(df))) * offset_meters
    random_angles = np.random.uniform(0, 2 * np.pi, size=len(df))

    lat_offset_m = random_distances * np.sin(random_angles)
    lon_offset_m = random_distances * np.cos(random_angles)

    lat_offset_deg = lat_offset_m / earth_radius * (180 / np.pi)
    lon_offset_deg = lon_offset_m / (earth_radius * np.cos(np.radians(df[lat_col]))) * (180 / np.pi)

    # Create a new DataFrame with jittered points
    jittered_df = pd.DataFrame({
        'lat_jittered': df[lat_col] + lat_offset_deg,
        'lon_jittered': df[lon_col] + lon_offset_deg,
        'original_index': df.index # Keep track of original position
    })
    
    # Convert to a GeoDataFrame to perform a single, fast spatial check
    gdf_jittered = gpd.GeoDataFrame(
        jittered_df, 
        geometry=gpd.points_from_xy(jittered_df.lon_jittered, jittered_df.lat_jittered),
        crs="EPSG:4326" # Standard lat/lon CRS
    )
    
    boundary_gdf = gpd.GeoDataFrame([{'geometry': boundary}], crs="EPSG:4326")

    # Use a spatial join to find all points inside the boundary at once
    valid_points = gpd.sjoin(gdf_jittered, boundary_gdf, how="inner", predicate="within")
    
    # Identify the small number of invalid points that need to be fixed
    invalid_indices = jittered_df[~jittered_df['original_index'].isin(valid_points['original_index'])].original_index
    
    if not invalid_indices.empty:
        print(f"Found {len(invalid_indices)} points outside the boundary. Re-processing them...")
        # Fall back to the slower, iterative method ONLY for these few points
        fixed_points_df = jitter_coordinates_with_boundary(df.loc[invalid_indices], lat_col, lon_col, offset_meters, boundary)
        
        # Combine the initially valid points with the newly fixed ones
        final_df = pd.concat([
            valid_points[['lat_jittered', 'lon_jittered']],
            fixed_points_df
        ], ignore_index=True)
    else:
        print("All points were generated within the boundary on the first try!")
        final_df = valid_points[['lat_jittered', 'lon_jittered']]

    print(f"Fast anonymization complete for {len(final_df)} records.")
    return final_df

def jitter_coordinates_with_boundary(df, lat_col, lon_col, offset_meters, boundary):
    
    # Applies a random offset to coordinates, ensuring they stay within the provided boundary.
    # This is a slower, iterative method used only for points that failed the fast vectorized check.
    print(f"Applying bounded offset of up to {offset_meters} meters...")
    earth_radius = 6378137
    jittered_points = []

    for index, row in df.iterrows():
        original_lat = row[lat_col]
        original_lon = row[lon_col]
        
        while True: # Loop until a valid point is found
            # Generate a single random offset
            random_distance = np.sqrt(np.random.uniform(0, 1)) * offset_meters
            random_angle = np.random.uniform(0, 2 * np.pi)

            # Calculate offsets in meters
            lat_offset_m = random_distance * np.sin(random_angle)
            lon_offset_m = random_distance * np.cos(random_angle)
            
            # Convert meter offsets to degree offsets
            lat_offset_deg = lat_offset_m / earth_radius * (180 / np.pi)
            lon_offset_deg = lon_offset_m / (earth_radius * np.cos(np.radians(original_lat))) * (180 / np.pi)

            # Create the new point
            new_lat = original_lat + lat_offset_deg
            new_lon = original_lon + lon_offset_deg
            new_point = Point(new_lon, new_lat) 

            # Check if the point is inside the boundary
            if boundary.contains(new_point):
                jittered_points.append({'lat_jittered': new_lat, 'lon_jittered': new_lon})
                break
    
    print(f"Anonymization complete for {len(jittered_points)} records.")
    return pd.DataFrame(jittered_points)


def create_continental_us_boundary_with_margin(shapefile_path, buffer_meters=5000):
    ###
    # Loads a US nation shapefile and returns a polygon for the continental US
    # with an optional buffer (margin) applied to the boundary.
    ###
    print("Loading US boundary shapefile...")
    us_gdf = gpd.read_file(shapefile_path)

    # The 'nation' file has one row. Get its geometry object.
    all_us_parts = us_gdf.iloc[0].geometry

    # Union all polygons in the MultiPolygon (includes Keys and other small islands)
    continental_us = all_us_parts.buffer(0)  # buffer(0) fixes invalid geometries

    # Apply a buffer to the boundary (convert meters to degrees)
    earth_radius = 6378137  # Earth's radius in meters
    buffer_degrees = buffer_meters / earth_radius * (180 / np.pi)
    buffered_polygon = continental_us.buffer(buffer_degrees)

    print(f"Boundary for continental US created with a {buffer_meters}m margin.")
    return buffered_polygon


source_lat_col = 'lat'
source_lon_col = 'long'
output_dir = 'public'
output_html_file = os.path.join(output_dir, 'anonymous_heatmap.html')
us_shapefile = 'data/cb_2018_us_nation_5m.shp' 
PRIVACY_RADIUS_METERS = 500


try:
    aws_key = os.getenv('HEATMAP_AWS_ACCESS_KEY_ID')
    aws_secret = os.getenv('HEATMAP_AWS_SECRET_ACCESS_KEY')
    bucket_name = os.getenv('HEATMAP_S3_BUCKET_NAME')
    file_key = os.getenv('HEATMAP_S3_FILE_KEY')

    if not all([aws_key, aws_secret, bucket_name, file_key]):
        raise ValueError("Missing required AWS environment variables for S3 access.")

    s3_client = boto3.client(
        's3',
        aws_access_key_id=aws_key,
        aws_secret_access_key=aws_secret
    )

    # Create the US boundary to check against
    us_boundary = create_continental_us_boundary_with_margin(us_shapefile, buffer_meters=5000)

    # Put the single boundary polygon into a GeoDataFrame for spatial join
    boundary_gdf = gpd.GeoDataFrame([{'geometry': us_boundary}], crs="EPSG:4326")

    # Get source data from S3 and load it into dataframe
    s3_object = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    csv_data = s3_object['Body'].read()

    source_df = pd.read_csv(io.BytesIO(csv_data))
    source_df.dropna(subset=[source_lat_col, source_lon_col], inplace=True)

    print(f"Loaded {len(source_df)} total records with coordinates.")

    # Keep only points already inside the US boundary
    print("Pre-filtering source data to find points within the continental US...")
    source_gdf = gpd.GeoDataFrame(
        source_df,
        geometry=gpd.points_from_xy(source_df[source_lon_col], source_df[source_lat_col]),
        crs="EPSG:4326"
    )

    # Use a fast spatial join to find members inside the boundary
    continental_us_members = gpd.sjoin(source_gdf, boundary_gdf, how="inner", predicate="within")
    
    original_count = len(source_df)
    filtered_count = len(continental_us_members)
    discarded_count = original_count - filtered_count

    print(f"Kept {filtered_count} records within the continental US boundary.")
    if discarded_count > 0:
        print(f"Discarded {discarded_count} records located outside the boundary (e.g., AK, HI, PR, or data errors).")

    # Anonymize ONLY pre-filtered data
    if filtered_count > 0:
        anonymized_df = fast_jitter_with_boundary(
            continental_us_members.drop(columns=['index_right']), # Drop column added by sjoin
            source_lat_col,
            source_lon_col,
            PRIVACY_RADIUS_METERS,
            us_boundary
        )

        # Create heatmap
        map_center = [39.82, -98.57]
        map_bounds = [[24, -125], [50, -66]] # Approx. bounds for continental US

        m = folium.Map(
            location=map_center, 
            zoom_start=5, 
            tiles='CartoDB positron', 
            max_bounds=map_bounds, 
            min_zoom=4,
            zoom_delta=0.5,
            zoom_snap=0.5
        )
        m.fit_bounds(map_bounds)
        heatmap_data = anonymized_df[['lat_jittered', 'lon_jittered']].values.tolist()
        HeatMap(heatmap_data, radius=8, blur=5).add_to(m)

        # Add a simple color legend to the map
        legend_html = '''
            <div style="position: fixed; 
            bottom: 50px; left: 50px; width: 150px; height: 90px; 
            border:2px solid grey; z-index:9999; font-size:14px;
            background-color:white;
            ">&nbsp; <b>Density</b> <br>
            &nbsp; High &nbsp; <i class="fa fa-square" style="color:red"></i><br>
            &nbsp; Medium &nbsp; <i class="fa fa-square" style="color:yellowgreen"></i><br>
            &nbsp; Low &nbsp; <i class="fa fa-square" style="color:blue"></i>
            </div>
            '''
        m.get_root().html.add_child(folium.Element(legend_html))

        # Save Map
        m.save(output_html_file)
        print(f"Heatmap saved to '{output_html_file}'.")
    else:
        print("No source data points were found within the continental US. Cannot generate a heatmap.")

except FileNotFoundError:
    print(f"Error: A required file was not found. Check paths for '{csv_data}' and '{us_shapefile}'.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")