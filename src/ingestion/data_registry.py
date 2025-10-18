"""
Central registry for real-world pole verification data feeds.

Each entry documents where the feed is expected to live on disk, what
file formats the pipeline supports, and which loader function should be
used once credentials/dumps are available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from config import DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, IMAGERY_DIR


@dataclass
class DataSourceSpec:
    """Descriptor for an external data feed used in verification."""

    name: str
    category: str
    description: str
    expected_paths: List[Path]
    loader_hint: str
    documentation: Optional[str] = None
    required: bool = False
    notes: Optional[str] = None
    exists: bool = field(init=False, default=False)
    missing_paths: List[Path] = field(init=False, default_factory=list)

    def probe(self) -> None:
        """Populate existence flags for downstream logging."""
        self.missing_paths = [path for path in self.expected_paths if not path.exists()]
        self.exists = len(self.missing_paths) == 0


def _p(*parts: str) -> Path:
    """Utility to build paths relative to the project data directory."""
    return DATA_DIR.joinpath(*parts)


DATA_SOURCES: Dict[str, DataSourceSpec] = {
    "verizon_gis": DataSourceSpec(
        name="Verizon Enterprise GIS",
        category="Authoritative Inventory",
        description="Internal Verizon pole inventory with inspection metadata, ownership, attachments.",
        expected_paths=[
            RAW_DATA_DIR / "verizon" / "pole_inventory.geojson",
            RAW_DATA_DIR / "verizon" / "inspection_ledger.csv",
        ],
        loader_hint="Create secure connector in src/ingestion/verizon_loader.py to pull nightly dumps.",
        documentation="Coordinate with Verizon GIS ops for SFTP/API credentials; avoid storing secrets in repo.",
        required=True,
        notes="Once available, merge with OSM feed inside run_pilot._load_historical_poles().",
    ),
    "state_permitting": DataSourceSpec(
        name="State & County Utility Permits",
        category="Authoritative Inventory",
        description="PennDOT/municipal permit exports covering pole installs, relocations, and retirements.",
        expected_paths=[
            RAW_DATA_DIR / "pennsylvania" / "utility_permits.csv",
            RAW_DATA_DIR / "municipal" / "asset_registry.geojson",
        ],
        loader_hint="Add parsers under src/ingestion/state_permits.py to normalise schemas.",
        documentation="Check PennDOT OpenData, city data portals; prioritise CSV/GeoJSON dumps.",
    ),
    "commercial_aerial": DataSourceSpec(
        name="Commercial Aerial Imagery",
        category="Imagery",
        description="Leaf-on/off 30 cm imagery tiles (Maxar, Planet, or state orthos) covering Harrisburg AOI.",
        expected_paths=[
            IMAGERY_DIR / "maxar_tiles",
            IMAGERY_DIR / "planet_tiles",
        ],
        loader_hint="Extend src/detection/tile_catalog.py to index new raster directories before YOLO runs.",
        documentation="Capture acquisition metadata (timestamp, sun angle) in tileset_manifest.json.",
    ),
    "street_level": DataSourceSpec(
        name="Street-Level Imagery",
        category="Street Imagery",
        description="Mapillary / Kinetik panoramas for corridor QA and hard-negative mining.",
        expected_paths=[
            RAW_DATA_DIR / "street_level" / "mapillary" / "images",
            RAW_DATA_DIR / "street_level" / "mapillary" / "mapillary_metadata.csv",
        ],
        loader_hint="Use src/utils/harvest_mapillary.py then extend ingestion/street_level.py for labeling queue.",
        documentation="Requires MAPILLARY_TOKEN or similar API keys set via environment variables.",
    ),
    "pamap_orthophotos": DataSourceSpec(
        name="PAMAP Leaf-Off Orthophotos",
        category="Imagery",
        description="Pennsylvania leaf-off aerial imagery (6–12 inch) for high-resolution detection reruns.",
        expected_paths=[IMAGERY_DIR / "pamap" / "tiles" / "pemaimagery_2021_2023_harrisburg.png",
                        IMAGERY_DIR / "pamap" / "tileset_manifest.json"],
        loader_hint="Use state download scripts under src/ingestion/pamap_downloader.py to sync GeoTIFFs.",
        documentation="Available via PA Spatial Data Access (PASDA); ensure CRS metadata stored alongside tiles.",
    ),
    "naip_historical": DataSourceSpec(
        name="NAIP Historical Imagery",
        category="Imagery",
        description="Prior-year NAIP tiles for multi-season training and change detection.",
        expected_paths=[
            IMAGERY_DIR / "naip_historical",
        ],
        loader_hint="Organise per-year subfolders; extend detection tile catalog to use seasonal variants.",
        documentation="Download from USDA NRCS Geospatial Data Gateway (public domain).",
    ),
    "usgs_3dep_extended": DataSourceSpec(
        name="USGS 3DEP Point Clouds",
        category="Elevation",
        description="Expanded Harrisburg 3DEP LAS/LAZ tiles for pole height derivation.",
        expected_paths=[
            PROCESSED_DATA_DIR / "lidar" / "pointclouds",
            PROCESSED_DATA_DIR / "lidar" / "dsm_tiles",
        ],
        loader_hint="Run src/ingestion/lidar_pipeline.py to convert point clouds to DSM/DTM rasters.",
        documentation="Fetch from USGS 3DEP AWS (public domain).",
    ),
    "nlcd_landcover": DataSourceSpec(
        name="National Land Cover Dataset",
        category="Context",
        description="Land-cover raster to identify forest, wetlands, and built-up areas for contextual scoring.",
        expected_paths=[PROCESSED_DATA_DIR / "context" / "nlcd_2019_harrisburg.tif"],
        loader_hint="Download via USGS MRLC; store reprojected raster matching AOI.",
        documentation="Public domain; metadata required for provenance.",
    ),
    "nhd_hydrography": DataSourceSpec(
        name="National Hydrography Dataset",
        category="Context",
        description="High-resolution hydro polygons/lines to mask rivers and lakes.",
        expected_paths=[
            PROCESSED_DATA_DIR / "context" / "nhd_water.geojson",
        ],
        loader_hint="Use src/ingestion/nhd_ingest.py to subset Harrisburg HUCs and simplify geometries.",
        documentation="Freely available via USGS NHD download services.",
    ),
    "tiger_roads": DataSourceSpec(
        name="TIGER + PennDOT Roads",
        category="Context",
        description="Merged TIGER/PennDOT road centerlines for ROW proximity checks.",
        expected_paths=[
            PROCESSED_DATA_DIR / "context" / "transport_roads.geojson",
        ],
        loader_hint="Combine Census TIGER shapefiles with PennDOT centerlines under src/ingestion/road_loader.py.",
        documentation="Census TIGER (public domain) plus PennDOT open data license.",
    ),
    "fcc_asr": DataSourceSpec(
        name="FCC Antenna Structure Registration",
        category="Infrastructure",
        description="Registered towers to help distinguish poles from tall structures.",
        expected_paths=[
            RAW_DATA_DIR / "fcc" / "antenna_structures.csv",
        ],
        loader_hint="Download weekly ASR CSV and parse via src/ingestion/fcc_asr_loader.py.",
        documentation="FCC ASR public download (CSV).",
    ),
    "hifld_energy": DataSourceSpec(
        name="HIFLD Energy Infrastructure",
        category="Infrastructure",
        description="Highway Infrastructure Foundation Level Data – energy asset points/lines.",
        expected_paths=[
            RAW_DATA_DIR / "hifld" / "energy_assets.geojson",
        ],
        loader_hint="Use DHS/HIFLD open datasets to capture substations, transmission lines, etc.",
        documentation="HIFLD open data license; review usage terms.",
    ),
    "municipal_open_data": DataSourceSpec(
        name="Municipal Harrisburg Assets",
        category="Authoritative Inventory",
        description="City/County asset registries or permit logs to corroborate OSM poles.",
        expected_paths=[
            RAW_DATA_DIR / "municipal" / "harrisburg_assets.geojson",
        ],
        loader_hint="Scrape CS/Harrisburg open data portal via src/ingestion/municipal_loader.py.",
        documentation="Check municipality-specific licensing terms before redistribution.",
    ),
    "mapillary_refresh": DataSourceSpec(
        name="Mapillary Metadata Refresh",
        category="Street Imagery",
        description="Quarterly dumps of Mapillary metadata for corridors, enabling labeling campaigns.",
        expected_paths=[
            RAW_DATA_DIR / "street_level" / "mapillary" / "mapillary_metadata.csv",
        ],
        loader_hint="Schedule harvest_mapillary.py with date filters; store incremental snapshots.",
        documentation="Requires MAPILLARY_TOKEN with proper scopes.",
    ),
    "lidar_pointcloud": DataSourceSpec(
        name="USGS / Enterprise LiDAR",
        category="Elevation",
        description="Classified point clouds or DSM rasters for pole height estimation and vegetation clearance.",
        expected_paths=[
            PROCESSED_DATA_DIR / "lidar" / "pointclouds",
            PROCESSED_DATA_DIR / "lidar" / "dsm_tiles",
        ],
        loader_hint="Add processing routines to src/ingestion/lidar_pipeline.py to derive pole height rasters.",
        documentation="USGS 3DEP available via AWS Open Data; enterprise mobile LiDAR via secure share.",
    ),
    "vegetation_row": DataSourceSpec(
        name="ROW & Vegetation Layers",
        category="Context",
        description="Utility easements, land-cover, weather/outage overlays to refine contextual scores.",
        expected_paths=[
            PROCESSED_DATA_DIR / "context" / "utility_row.geojson",
            PROCESSED_DATA_DIR / "context" / "land_cover.tif",
        ],
        loader_hint="Augment src/fusion/context_filters.py to consume new rasters/vectors.",
    ),
    "compliance_filings": DataSourceSpec(
        name="FCC Compliance Filings",
        category="Compliance",
        description="Pole attachment reports, outage logs, or third-party audit results.",
        expected_paths=[
            RAW_DATA_DIR / "fcc" / "pole_attachment.csv",
            RAW_DATA_DIR / "compliance" / "outage_logs.csv",
        ],
        loader_hint="Parse filings under src/ingestion/compliance_loader.py and merge recency metrics.",
    ),
}


def probe_data_sources(keys: Optional[Iterable[str]] = None) -> Dict[str, Dict[str, object]]:
    """Return availability metadata for requested data sources."""
    summary: Dict[str, Dict[str, object]] = {}
    selected = keys or DATA_SOURCES.keys()
    for key in selected:
        spec = DATA_SOURCES[key]
        spec.probe()
        summary[key] = {
            "name": spec.name,
            "category": spec.category,
            "description": spec.description,
            "exists": spec.exists,
            "missing_paths": [str(path) for path in spec.missing_paths],
            "loader_hint": spec.loader_hint,
            "documentation": spec.documentation,
            "required": spec.required,
            "notes": spec.notes,
        }
    return summary


def write_status_report(output_path: Path) -> None:
    """Persist a JSON status report for dashboards or CLI."""
    report = probe_data_sources()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))


def print_status() -> None:
    """Pretty-print probe results to stdout."""
    report = probe_data_sources()
    for key, info in report.items():
        status = "✅" if info["exists"] else "⚠️"
        print(f"{status} {info['name']} ({key})")
        if not info["exists"]:
            missing = info["missing_paths"]
            if missing:
                print("   Missing:")
                for path in missing:
                    print(f"    - {path}")
        if info.get("loader_hint"):
            print(f"   Loader: {info['loader_hint']}")
        if info.get("documentation"):
            print(f"   Docs: {info['documentation']}")
        if info.get("notes"):
            print(f"   Notes: {info['notes']}")
        print()


if __name__ == "__main__":
    print_status()
