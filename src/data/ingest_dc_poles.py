"""
Ingest DC Utility Poles Dataset (1999)
Converts Maryland State Plane coordinates to WGS84 lat/lon
"""

import pandas as pd
from pathlib import Path
from pyproj import Transformer
import sys

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

RAW_DATA_DIR = PROJECT_ROOT / 'data' / 'raw' / 'additional_sources'
PROCESSED_DATA_DIR = PROJECT_ROOT / 'data' / 'processed'


def convert_dc_poles():
    """Convert DC poles from State Plane to WGS84"""
    print("Loading DC utility poles dataset (1999)...")

    # Read CSV
    input_file = RAW_DATA_DIR / 'dc_utility_poles_1999.csv'
    df = pd.read_csv(input_file)

    print(f"Loaded {len(df)} poles from DC dataset")
    print(f"Columns: {df.columns.tolist()}")

    # Filter to only utility poles (exclude street lights)
    df_utility = df[df['ELT_CODE'] == 7020].copy()
    print(f"Filtered to {len(df_utility)} utility poles (excluding street lights)")

    # The coordinates are in Maryland State Plane (EPSG:26985 - NAD83 / Maryland)
    # Need to convert to WGS84 (EPSG:4326)
    print("Converting coordinates from Maryland State Plane to WGS84...")

    transformer = Transformer.from_crs("EPSG:26985", "EPSG:4326", always_xy=True)

    # Convert X, Y to lon, lat
    lons, lats = transformer.transform(df_utility['X'].values, df_utility['Y'].values)

    df_utility['lon'] = lons
    df_utility['lat'] = lats

    # Create standardized output
    output_df = pd.DataFrame({
        'pole_id': df_utility['OBJECTID'].astype(str),
        'lat': df_utility['lat'],
        'lon': df_utility['lon'],
        'source': 'dc_gov_1999',
        'pole_type': df_utility['DESC_'],
        'original_x': df_utility['X'],
        'original_y': df_utility['Y'],
        'elt_id': df_utility['ELT_ID'],
    })

    # Filter to valid coordinates
    output_df = output_df[
        (output_df['lat'] >= 38.0) & (output_df['lat'] <= 39.0) &
        (output_df['lon'] >= -78.0) & (output_df['lon'] <= -76.0)
    ]

    print(f"Converted {len(output_df)} poles with valid DC-area coordinates")
    print(f"Lat range: {output_df['lat'].min():.4f} to {output_df['lat'].max():.4f}")
    print(f"Lon range: {output_df['lon'].min():.4f} to {output_df['lon'].max():.4f}")

    # Save to processed data
    output_file = PROCESSED_DATA_DIR / 'dc_poles_wgs84.csv'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_file, index=False)

    print(f"\nSaved converted poles to: {output_file}")
    print("\nSample of converted data:")
    print(output_df.head(10))

    return output_df


if __name__ == '__main__':
    df = convert_dc_poles()
    print("\n✅ DC poles ingestion complete!")
