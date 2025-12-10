import pandas as pd
import sys
import math

def mercator_to_wgs84(x, y):
    lon = (x / 20037508.34) * 180
    lat = (math.atan(math.exp((y / 20037508.34) * 180 * math.pi / 180)) * 360 / math.pi) - 90
    return lat, lon

# Load the CSV
csv_path = 'data/raw/ErosionandSedimentControlFacilities.csv'
print(f"Loading {csv_path}...")
df = pd.read_csv(csv_path)

print(f"Columns: {df.columns.tolist()}")
print(f"Total records: {len(df)}")

# Analyze types
print("\nTop 20 SUB_FACI_2 values:")
print(df['SUB_FACI_2'].value_counts().head(20))

print("\nTop 20 PRIMARY__2 values:")
print(df['PRIMARY__2'].value_counts().head(20))

# Filter for anything that looks like Utility/Transmission
keywords = ['UTILITY', 'TRANSMISSION', 'ELECTRIC', 'POLE', 'LINE', 'POWER']
relevant_df = df[
    df['SUB_FACI_2'].str.upper().str.contains('|'.join(keywords), na=False) |
    df['PRIMARY__3'].str.upper().str.contains('|'.join(keywords), na=False) | 
    df['SITE_NAME'].str.upper().str.contains('|'.join(keywords), na=False)
]

print(f"\nPotential Utility/Transmission Records: {len(relevant_df)}")
if not relevant_df.empty:
    print(relevant_df[['SITE_NAME', 'SUB_FACI_2', 'LAT', 'LNG']].head())

    # Check coordinates
    sample = relevant_df.iloc[0]
    lat_merc, lng_merc = sample['LAT'], sample['LNG']
    print(f"\nSample Raw Coordinates: {lat_merc}, {lng_merc}")

    # Manual conversion
    lat_deg, lon_deg = mercator_to_wgs84(lng_merc, lat_merc)
    print(f"Converted to WGS84: Lat={lat_deg}, Lon={lon_deg}")
    
    # Check if this falls in PA
    if 39 < lat_deg < 42.5 and -80.6 < lon_deg < -74.6:
        print("✓ Coordinate system likely EPSG:3857 (Web Mercator)")
    else:
        print("❌ Coordinate system NOT confirmed as EPSG:3857")
