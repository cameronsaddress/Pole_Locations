# Enterprise Data Source Catalog

This catalog tracks the external datasets we need to drive an enterprise-grade pole detection and validation workflow. Each entry includes the primary access point, notes gathered from public documentation, and the planned ingestion tasks.

---

## Aerial & Satellite Imagery

| Source | Description | Access | Planned Tasks |
| --- | --- | --- | --- |
| USDA NAIP (National Agriculture Imagery Program) | 1 m resolution leaf-on imagery, updated every 1–2 years. [NAIP overview](https://www.fsa.usda.gov/programs-and-services/aerial-photography/imagery-programs/naip-imagery/index) | `download_naip_pc.py` (AWS S3) | Expand downloader to pull latest 2024 tiles, capture tile metadata, publish md5 manifests. |
| Pennsylvania PAMAP Orthophotos | 0.5–1 ft leaf-off imagery via PASDA. | PASDA (`https://www.pasda.psu.edu/uci/` search “PAMAP”) | Add PAMAP fetch script, store in `data/imagery/pamap`, maintain metadata JSON. |
| Maxar/Planet Commercial Imagery (future) | 30 cm commercial tiles for enterprise corridors. | N/A (requires license) | Track licensing requirements; once approved, build download/tiling pipeline. |

## Street-Level Imagery

| Source | Description | Access | Planned Tasks |
| --- | --- | --- | --- |
| Mapillary API | Community street-level imagery with API for tiles + vector data. [Developer portal](https://www.mapillary.com/developer) | REST API (token) | Script: corridor imagery pull, keyframe extraction, label export pipeline. |
| KartaView (OpenStreetCam) | Open street-level imagery alternative. | `https://kartaview.org/developers` | Evaluate coverage; implement pull if Mapillary coverage is sparse. |

## Inventory & Context Feeds

| Source | Description | Access | Planned Tasks |
| --- | --- | --- | --- |
| FCC Antenna Structure Registration (ASR) | Tower locations, useful for context filtering. [FCC ASR data](https://www.fcc.gov/wireless/systems-utilities/antenna-structure-registration-asr/resources-data) | CSV download | Add to `data/raw/fcc/`, normalize schema, join with context filters. |
| HIFLD Energy Infrastructure | Nationwide utility infrastructure dataset. [HIFLD Open Data](https://hifld-geoplatform.opendata.arcgis.com/) | GeoJSON/CSV | Stage in `data/raw/hifld/`, extract pole-related features for hard negatives/context. |
| PennDOT / PennDOT Utility Permits | State permits and asset registries. [PA Open Data](https://data.pa.gov/) | API/CSV | Identify relevant datasets (permits, ROW); build nightly fetch job. |
| Municipal (Harrisburg/Dauphin County) Assets | Local inventories and permits. | City/County open data portals | Catalog available feeds, wire into fusion as supplementary corroboration. |
| OSM Poles | Existing baseline import (already in repo). | Overpass API | Continue refresh cadence; align with active learning loop. |

## Terrain & Land Cover

| Source | Description | Access | Planned Tasks |
| --- | --- | --- | --- |
| USGS 3DEP | LiDAR point clouds + DSM/DTM for pole height filtering. [USGS 3DEP Download](https://www.usgs.gov/core-science-systems/ngp/3dep) | Entwine/PDAL | Extend downloader to fetch missing tiles, generate DSM rasters. |
| National Land Cover Dataset (NLCD) | 30 m land-cover classification for masking. [USGS NLCD](https://www.mrlc.gov/data) | GeoTIFF | Download latest NLCD (2019/2021), clip to AOI, integrate into contextual filters. |
| National Hydrography Dataset (NHD) | Water bodies for false positive suppression. [USGS NHD](https://www.usgs.gov/national-hydrography/national-hydrography-dataset) | shapefile/GeoPackage | Pull high-resolution NHD for Harrisburg, persist under `data/processed/context/`. |
| TIGER / PennDOT Roads | Road centerlines for ROW snapping. [Census TIGER](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | Shapefile | Refresh road layers, merge with PennDOT data, feed into contextual filters. |

## Compliance & Operations

| Source | Description | Access | Planned Tasks |
| --- | --- | --- | --- |
| FCC Pole Attachment Filings / Outage Logs | Compliance datasets to cross-check inspection frequency. | FCC / State portals | Inventory feeds, parse compliance events, surface in dashboard. |
| Verizon GIS & Inspection Ledger (internal) | Enterprise authoritative inventory. | TBD (secure API) | Coordinate with enterprise team, define ingestion pipeline. |

---

### Next Steps
1. Prioritize ingestion scripts for NAIP 2024, PAMAP, Mapillary, FCC ASR, HIFLD, and USGS 3DEP.  
2. Track each pipeline in `TODO.md` under “Production-Grade Detection Roadmap.”  
3. As new feeds are confirmed, append to this catalog and assign implementation tasks.

