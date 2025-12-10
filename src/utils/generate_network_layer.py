import pandas as pd
import json
import math
from pathlib import Path
from scipy.spatial import cKDTree
import numpy as np

# Input/Output Paths
# Using the AI refined dataset if available, otherwise the verified source
INPUT_CSV = Path('data/processed/verified_poles_multi_source.csv')
OUTPUT_GEOJSON = Path('frontend-enterprise/public/pole_network.geojson')

def main():
    if not INPUT_CSV.exists():
        print(f"Error: {INPUT_CSV} not found.")
        return

    print(f"Loading {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    # Filter out low quality if needed (optional)
    # df = df[df['status'] != 'Missing']
    
    print(f"Processing {len(df)} poles for network generation...")
    
    # Extract coordinates
    coords = df[['lat', 'lon']].values
    
    # Convert to approximate meters for KDTree (simple projection)
    # lat_m ~= lat * 111111
    # lon_m ~= lon * 111111 * cos(lat)
    # We'll use a rough median lat for the lon scale
    median_lat = df['lat'].median()
    lon_scale = math.cos(math.radians(median_lat))
    
    points_m = np.column_stack([
        coords[:, 0] * 111111,
        coords[:, 1] * 111111 * lon_scale
    ])
    
    print("Building spatial index...")
    tree = cKDTree(points_m)
    
    # Query pairs within 150 meters (typical max span is ~50-100m, transmission can be longer)
    # We want to form lines, not a mesh. 
    # k=3 gets self + 2 neighbors.
    MAX_DIST_M = 150.0
    distances, indices = tree.query(points_m, k=3, distance_upper_bound=MAX_DIST_M)
    
    line_segments = []
    seen_pairs = set()
    
    print("Generating segments...")
    for i, (dists, idxs) in enumerate(zip(distances, indices)):
        # indices[0] is self (dist 0)
        # indices[1], indices[2] are neighbors
        
        for k in range(1, 3): # Check neighbor 1 and 2
            neighbor_idx = idxs[k]
            dist = dists[k]
            
            # infinite dist means no neighbor found within range
            if dist == float('inf'):
                continue
                
            # Create a sorted pair key to avoid duplicates (A-B and B-A)
            pair = tuple(sorted((i, neighbor_idx)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            
            # Add segment
            origin = coords[i]
            target = coords[neighbor_idx]
            
            # format for GeoJSON: [lon, lat] (Leaflet uses [lat, lon], GeoJSON uses [lon, lat])
            line_segments.append([
                [origin[1], origin[0]], 
                [target[1], target[0]]
            ])

    print(f"Created {len(line_segments)} connection segments.")
    
    # Construct GeoJSON FeatureCollection
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"type": "grid_network"},
                "geometry": {
                    "type": "MultiLineString",
                    "coordinates": line_segments
                }
            }
        ]
    }
    
    print(f"Saving to {OUTPUT_GEOJSON}...")
    OUTPUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_GEOJSON, 'w') as f:
        json.dump(geojson, f)
        
    print("✓ Network visualization layer generated.")

if __name__ == "__main__":
    main()
