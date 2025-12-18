
import requests
import math

# Coords for a pole in Dauphin County
LAT = 40.3685712
LON = -76.7152814

SOURCES = {
    "USGS": "https://basemap.nationalmap.gov/arcgis/services/USGSImageryOnly/MapServer/WMSServer",
    "PEMA_21_23": "https://imagery.pasda.psu.edu/arcgis/services/pasda/PEMAImagery2021_2023/MapServer/WMSServer",
    "NAIP_2022": "https://imagery.pasda.psu.edu/arcgis/services/pasda/NAIP2022WEB/MapServer/WMSServer",
    "PEMA_2018_2020": "https://imagery.pasda.psu.edu/arcgis/services/pasda/PEMAImagery2018_2020/MapServer/WMSServer"
}

def get_bbox(lat, lon):
    METERS_PER_WINDOW = 80.0
    half = METERS_PER_WINDOW / 2.0
    lat_delta = half / 111132.0
    lon_delta = half / (111132.0 * math.cos(math.radians(lat)))
    return f"{lon - lon_delta},{lat - lat_delta},{lon + lon_delta},{lat + lat_delta}"

bbox = get_bbox(LAT, LON)
print(f"BBOX: {bbox}")

for name, url in SOURCES.items():
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "BBOX": bbox,
        "SRS": "EPSG:4326",
        "WIDTH": "640",
        "HEIGHT": "640",
        "LAYERS": "0",
        "STYLES": "",
        "FORMAT": "image/jpeg"
    }
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Tester"}, timeout=5)
        if r.status_code == 200:
            print(f"{name}: {len(r.content)} bytes")
            with open(f"test_{name}.jpg", "wb") as f:
                f.write(r.content)
        else:
            print(f"{name}: Failed {r.status_code}")
    except Exception as e:
        print(f"{name}: Error {e}")
