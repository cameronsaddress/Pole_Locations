# New York Pole Inventory Sourcing Plan

Goal: replace OSM-only statewide inventory with authoritative pole datasets.

## Candidate Sources

1. **Con Edison (Downstate NY)**
   - Contact Con Edison GIS/Data Services (datarequests@coned.com).
   - Request latest distribution pole shapefile/CSV (attributes: pole ID, lat/lon, circuit, ownership).
   - Required agreement: NDA + data sharing MOU (refer Verizon legal template).

2. **NYSEG / RG&E (Avangrid)**
   - GIS Services: gis_services@nyseg.com.
   - Deliverable: county-level pole CSV or FGDB.
   - Ask for per-structure ID, install date, inspection status.

3. **National Grid (Upstate)**
   - Utility GIS requests via https://www.nationalgridus.com/Upstate-NY/Home/ContactUs.
   - Provide Verizon project overview; request export of overhead distribution structures.

4. **NYSDOT / NYSERDA open data**
   - Review https://data.ny.gov for existing pole/utility structure layers.
   - Many datasets require approval; log via Open Data request portal.

5. **Municipal open data portals**
   - NYC Open Data (https://data.cityofnewyork.us/): "Department of Transportation Street Lights" includes pole coordinates.
   - Syracuse, Rochester, Buffalo GIS portals (check for utility pole or streetlight inventories).
   - Script required to normalize formats.

## Ingestion Process

1. **Collect raw deliveries**
   - Store in `data/raw/ny_authoritative/<provider>/<YYYYMMDD>/`.
   - Accept formats: CSV, GeoJSON, Shapefile, FGDB.

2. **Conversion Script**
   ```bash
   PYTHONPATH=src ./venv/bin/python src/ingestion/ny_merge_authoritative_poles.py \
     --input-folder data/raw/ny_authoritative \
     --output data/processed/ny_authoritative_poles.csv
   ```
   - Script (TODO) will:
     - project all geometries to EPSG:4326,
     - harmonize column names (`pole_id`, `lat`, `lon`, `owner`, `source`),
     - deduplicate by pole_id and location tolerance (5 m).

3. **Fallback Handling**
   - When county-level gap remains, retain OSM placeholder but flag `source=osm_placeholder` for QA.

4. **Integration**
   - Update `sync_new_york_counties.py` to prefer authoritative CSVs when available (lookup by county slug).
   - Keep OSM data only as backup.

## Next Steps

- Draft outreach email template (include Verizon contact, requested format, security request).
- Track responses in `docs/ny_inventory_status.xlsx` (create tracker).
- Once first dataset received, build `ny_merge_authoritative_poles.py` to automate normalization.
