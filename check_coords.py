
import json
with open("data/processed/grid_backbone.geojson") as f:
    data = json.load(f)

print(f"Total Features: {len(data['features'])}")
first_pole = next((f for f in data['features'] if f["geometry"]["type"] == "Point"), None)
if first_pole:
    coords = first_pole["geometry"]["coordinates"]
    print(f"First Pole: {coords} (Lon, Lat)")
