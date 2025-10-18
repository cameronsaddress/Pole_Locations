"""
Load and standardize pole location data from various sources
"""
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path
import logging
from typing import Optional
import sys

sys.path.append(str(Path(__file__).parent.parent))
from config import (
    CRS_STANDARD, EAST_COAST_BBOX, BUFFER_DISTANCE_METERS,
    RAW_DATA_DIR, PROCESSED_DATA_DIR
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PoleDataLoader:
    """Load and standardize pole location data"""

    def __init__(self):
        self.crs = CRS_STANDARD
        self.bbox = EAST_COAST_BBOX

    def load_csv(self, filepath: Path, lat_col='lat', lon_col='lon') -> gpd.GeoDataFrame:
        """
        Load pole data from CSV file and convert to GeoDataFrame

        Args:
            filepath: Path to CSV file
            lat_col: Name of latitude column
            lon_col: Name of longitude column

        Returns:
            GeoDataFrame with pole locations in EPSG:4326
        """
        logger.info(f"Loading pole data from {filepath}")

        # Load CSV
        df = pd.read_csv(filepath)
        logger.info(f"Loaded {len(df):,} records")

        # Check required columns
        if lat_col not in df.columns or lon_col not in df.columns:
            raise ValueError(f"CSV must contain '{lat_col}' and '{lon_col}' columns")

        # Remove rows with missing coordinates
        initial_count = len(df)
        df = df.dropna(subset=[lat_col, lon_col])
        if len(df) < initial_count:
            logger.warning(f"Removed {initial_count - len(df)} rows with missing coordinates")

        # Create geometry from lat/lon
        geometry = [Point(lon, lat) for lon, lat in zip(df[lon_col], df[lat_col])]

        # Create GeoDataFrame
        gdf = gpd.GeoDataFrame(df, geometry=geometry, crs=self.crs)

        logger.info(f"Created GeoDataFrame with {len(gdf):,} poles in {self.crs}")

        return gdf

    def filter_by_bbox(self, gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Filter poles to East Coast bounding box

        Args:
            gdf: GeoDataFrame with pole locations

        Returns:
            Filtered GeoDataFrame
        """
        logger.info("Filtering poles to East Coast bounding box")

        initial_count = len(gdf)

        # Ensure correct CRS
        if gdf.crs != self.crs:
            logger.info(f"Reprojecting from {gdf.crs} to {self.crs}")
            gdf = gdf.to_crs(self.crs)

        # Filter by bounding box
        filtered = gdf.cx[
            self.bbox['minx']:self.bbox['maxx'],
            self.bbox['miny']:self.bbox['maxy']
        ]

        removed = initial_count - len(filtered)
        if removed > 0:
            logger.warning(f"Removed {removed:,} poles outside East Coast bbox")

        logger.info(f"Retained {len(filtered):,} poles within bbox")

        return filtered

    def create_buffers(self, gdf: gpd.GeoDataFrame, buffer_meters: float = BUFFER_DISTANCE_METERS) -> gpd.GeoDataFrame:
        """
        Create buffer zones around pole locations for imagery extraction

        Args:
            gdf: GeoDataFrame with pole locations
            buffer_meters: Buffer distance in meters

        Returns:
            GeoDataFrame with buffer geometries
        """
        logger.info(f"Creating {buffer_meters}m buffers around {len(gdf):,} poles")

        # Create a copy to avoid modifying original
        buffered = gdf.copy()

        # For EPSG:4326 (degrees), approximate meters to degrees
        # At mid-latitudes (~40°), 1 degree ≈ 111km
        # So buffer in degrees ≈ buffer_meters / 111000
        buffer_degrees = buffer_meters / 111000

        # Create buffers
        buffered['buffer_geometry'] = buffered.geometry.buffer(buffer_degrees)

        logger.info(f"Created buffer zones (approx {buffer_meters}m)")

        return buffered

    def validate_data(self, gdf: gpd.GeoDataFrame) -> dict:
        """
        Validate pole data quality and return statistics

        Args:
            gdf: GeoDataFrame with pole data

        Returns:
            Dictionary with validation statistics
        """
        logger.info("Validating pole data quality")

        stats = {
            'total_records': len(gdf),
            'crs': str(gdf.crs),
            'bbox': {
                'min_lon': gdf.geometry.x.min(),
                'max_lon': gdf.geometry.x.max(),
                'min_lat': gdf.geometry.y.min(),
                'max_lat': gdf.geometry.y.max()
            },
            'missing_values': {
                col: gdf[col].isna().sum()
                for col in gdf.columns if col != 'geometry'
            },
            'duplicates': gdf.duplicated(subset=['pole_id'] if 'pole_id' in gdf.columns else None).sum()
        }

        # Check for invalid coordinates
        invalid_coords = (
            (gdf.geometry.x < -180) | (gdf.geometry.x > 180) |
            (gdf.geometry.y < -90) | (gdf.geometry.y > 90)
        ).sum()
        stats['invalid_coordinates'] = invalid_coords

        # Log findings
        logger.info(f"Validation complete: {stats['total_records']:,} records")
        if invalid_coords > 0:
            logger.warning(f"Found {invalid_coords} invalid coordinates")
        if stats['duplicates'] > 0:
            logger.warning(f"Found {stats['duplicates']} duplicate pole_ids")

        return stats

    def save_geojson(self, gdf: gpd.GeoDataFrame, filename: str, use_buffer_geometry: bool = False) -> Path:
        """
        Save GeoDataFrame to GeoJSON format

        Args:
            gdf: GeoDataFrame to save
            filename: Output filename
            use_buffer_geometry: If True, use 'buffer_geometry' column as active geometry

        Returns:
            Path to saved file
        """
        output_path = PROCESSED_DATA_DIR / filename

        # Handle multiple geometry columns
        gdf_to_save = gdf.copy()
        if use_buffer_geometry and 'buffer_geometry' in gdf_to_save.columns:
            # Set buffer as active geometry and drop original
            gdf_to_save = gdf_to_save.set_geometry('buffer_geometry')
            gdf_to_save = gdf_to_save.drop(columns=['geometry'])

        gdf_to_save.to_file(output_path, driver='GeoJSON')
        logger.info(f"Saved {len(gdf_to_save):,} records to {output_path}")
        return output_path


def main():
    """
    Main pipeline for loading and preprocessing pole data
    """
    logger.info("=" * 60)
    logger.info("POLE DATA INGESTION PIPELINE")
    logger.info("=" * 60)

    # Initialize loader
    loader = PoleDataLoader()

    # Load real pole inventory downloaded from OpenStreetMap
    input_file = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
    if not input_file.exists():
        raise FileNotFoundError(
            f"Missing {input_file}. Run `python src/utils/get_osm_poles.py` "
            "to download the real pole inventory before executing the ingestion pipeline."
        )

    gdf = loader.load_csv(input_file)

    # Filter to East Coast
    gdf = loader.filter_by_bbox(gdf)

    # Validate data
    stats = loader.validate_data(gdf)
    print("\nData Validation Stats:")
    print(f"  Total records: {stats['total_records']:,}")
    print(f"  CRS: {stats['crs']}")
    print(f"  Lat range: {stats['bbox']['min_lat']:.4f} to {stats['bbox']['max_lat']:.4f}")
    print(f"  Lon range: {stats['bbox']['min_lon']:.4f} to {stats['bbox']['max_lon']:.4f}")
    print(f"  Duplicates: {stats['duplicates']}")
    print(f"  Invalid coords: {stats['invalid_coordinates']}")

    # Create buffers
    gdf_buffered = loader.create_buffers(gdf)

    # Save to GeoJSON
    output_path = loader.save_geojson(gdf, 'poles_processed.geojson')
    buffer_path = loader.save_geojson(gdf_buffered, 'poles_with_buffers.geojson', use_buffer_geometry=True)

    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Processed poles: {output_path}")
    logger.info(f"  Buffered poles: {buffer_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
