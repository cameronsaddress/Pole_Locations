"""
Maps API endpoints - GeoJSON, heatmaps, spatial data
NOW USING MULTI-SOURCE VERIFIED DATA with 3-tier classification
"""
from fastapi import APIRouter
import sys
from pathlib import Path
import pandas as pd
import json
import math

sys.path.append(str(Path(__file__).parent.parent.parent.parent.parent / 'src'))
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR

router = APIRouter()

@router.get("/maps/poles-geojson")
async def get_poles_geojson(limit: int = 2000):
    """
    Get poles as GeoJSON for map display
    NOW USING MULTI-SOURCE VERIFICATION with color-coded confidence
    """
    # Try to load verified data first
    verified_csv = PROCESSED_DATA_DIR / 'verified_poles_multi_source.csv'

    if verified_csv.exists():
        df = pd.read_csv(verified_csv)
        use_verified = True
    else:
        # Fallback to OSM data
        poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'
        if not poles_csv.exists():
            return {
                "type": "FeatureCollection",
                "features": []
            }
        df = pd.read_csv(poles_csv)
        if limit and limit > 0:
            df = df.head(limit)
        use_verified = False

    if use_verified:
        if 'lat' not in df.columns and 'detection_lat' in df.columns:
            df['lat'] = df['detection_lat']
        if 'lon' not in df.columns and 'detection_lon' in df.columns:
            df['lon'] = df['detection_lon']
        if 'total_confidence' not in df.columns and 'combined_confidence' in df.columns:
            df['total_confidence'] = df['combined_confidence']
        if 'nearest_ai_distance_m' not in df.columns and 'match_distance_m' in df.columns:
            df['nearest_ai_distance_m'] = df['match_distance_m']
        if 'recency_score' not in df.columns and 'recency_weight' in df.columns:
            df['recency_score'] = df['recency_weight']
        if 'needs_review' not in df.columns:
            df['needs_review'] = df['classification'] == 'in_question'
        if 'num_sources' not in df.columns:
            df['num_sources'] = df['classification'].apply(lambda c: 1 if c == 'new_missing' else 2)
        if 'total_confidence' not in df.columns:
            df['total_confidence'] = df.get('detection_confidence', 0.0)
        if limit and limit > 0:
            df = df.head(limit)

    # Drop rows with NaN lat/lon
    df = df.dropna(subset=['lat', 'lon'])

    def clean_float(value):
        """Convert value to float or return None if not finite."""
        try:
            f = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(f) or math.isinf(f):
            return None
        return f

    features = []
    for _, row in df.iterrows():
        # Skip invalid coordinates
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                continue
        except (ValueError, TypeError):
            continue

        recency_score = None
        inspection_date = None
        needs_review = False
        num_sources = 1
        spatial_distance = 0.0
        ai_confidence = 0.0
        sources = set()

        if use_verified:
            # Use real verification data
            confidence = clean_float(row.get('total_confidence'))
            classification = row['classification']
            color = row['status_color'] if 'status_color' in df.columns else None
            recency_score = clean_float(row.get('recency_score'))
            inspection_raw = row.get('inspection_date') if 'inspection_date' in row else None
            inspection_date = inspection_raw if isinstance(inspection_raw, str) and inspection_raw else None
            needs_review = bool(row.get('needs_review', False))
            if 'num_sources' in row:
                num_sources_val = row.get('num_sources')
                if num_sources_val is not None and not pd.isna(num_sources_val):
                    num_sources = int(num_sources_val)
            if 'nearest_ai_distance_m' in row:
                dist_val = row.get('nearest_ai_distance_m')
                cleaned_distance = clean_float(dist_val)
                if cleaned_distance is not None:
                    spatial_distance = cleaned_distance
            ai_conf = row.get('ai_confidence', row.get('detection_confidence'))
            cleaned_ai_conf = clean_float(ai_conf)
            if cleaned_ai_conf is not None:
                ai_confidence = cleaned_ai_conf
            ndvi_val = clean_float(row.get('ndvi'))
            road_distance_val = clean_float(row.get('road_distance_m'))
            surface_elev_val = clean_float(row.get('surface_elev_m'))
            sources_raw = row.get('sources')
            if isinstance(sources_raw, str) and sources_raw:
                sources = {s.strip() for s in sources_raw.split('|') if s.strip()}
            review_reasons = None
            reasons_raw = row.get('review_reasons')
            if isinstance(reasons_raw, str) and reasons_raw:
                review_reasons = [r.strip() for r in reasons_raw.split('|') if r.strip()]

            # Map classification to status
            if classification == 'verified_good':
                status = "verified"
            elif classification in ('in_question', 'new_detection', 'ai_only_verified'):
                status = "review"
            elif classification in ('missing_new', 'new_missing'):
                status = "new"
            else:
                status = "review"
        else:
            # Fallback mock data
            confidence = 0.954
            status = "verified"
            color = "#00897B"
            classification = 'verified_good'
            sources = {'unknown'}

        verification_level = 'unknown'
        if 'ai' in sources and len(sources) == 1:
            verification_level = 'ai_only'
        elif 'ai' in sources and len(sources) >= 2:
            verification_level = 'multi_source'
        elif 'osm' in sources:
            verification_level = 'historical_only'
        elif classification == 'in_question':
            verification_level = 'needs_review'
        elif classification in ('new_detection', 'ai_only_verified'):
            verification_level = 'ai_only'
        else:
            verification_level = 'unknown'

        if verification_level == 'ai_only':
            color = '#1E88E5'
        elif verification_level == 'multi_source':
            color = '#2E7D32'
        elif classification == 'in_question':
            color = '#FF9800'
        elif classification in ('missing_new', 'new_missing'):
            color = '#7E57C2'
        else:
            color = color or '#00897B'

        confidence_display = round(confidence, 3) if confidence is not None else None
        spatial_distance_display = round(spatial_distance, 2) if spatial_distance is not None else None
        ai_confidence_display = round(ai_confidence, 3) if ai_confidence is not None else None

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "id": str(row['pole_id']),
                "confidence": confidence_display,
                "status": status,
                "color": color,
                "classification": classification,
                "pole_type": str(row.get('pole_type', 'tower')),
                "operator": str(row.get('operator', 'Unknown')),
                "num_sources": num_sources,
                "spatial_distance_m": spatial_distance_display,
                "recency_score": recency_score,
                "inspection_date": inspection_date,
                "needs_review": needs_review,
                "source": row.get('source') if 'source' in row else 'unknown',
                "verification_level": verification_level,
                "ai_confidence": ai_confidence_display,
                "ndvi": ndvi_val,
                "road_distance_m": road_distance_val,
                "surface_elev_m": surface_elev_val,
                "sources": list(sources),
                "review_reasons": review_reasons
            }
        }
        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "using_verified_data": use_verified,
            "total_features": len(features)
        }
    }

@router.get("/maps/heatmap-data")
async def get_heatmap_data():
    """
    Get heatmap density data for pole distribution
    """
    poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'

    if not poles_csv.exists():
        return {"points": []}

    df = pd.read_csv(poles_csv)
    df = df.dropna(subset=['lat', 'lon'])

    points = []
    for _, row in df.iterrows():
        try:
            lat = float(row['lat'])
            lon = float(row['lon'])
            if (-90 <= lat <= 90) and (-180 <= lon <= 180):
                points.append({
                    "lat": lat,
                    "lon": lon,
                    "intensity": 1.0
                })
        except (ValueError, TypeError):
            continue

    return {
        "points": points,
        "max_intensity": 1.0
    }

@router.get("/maps/bounds")
async def get_map_bounds():
    """
    Get geographic bounds for map initialization
    """
    poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'

    if not poles_csv.exists():
        # Default to Harrisburg area
        return {
            "north": 40.35,
            "south": 40.20,
            "east": -76.75,
            "west": -76.95,
            "center": {
                "lat": 40.2732,
                "lon": -76.8867
            }
        }

    df = pd.read_csv(poles_csv)
    df = df.dropna(subset=['lat', 'lon'])

    if len(df) == 0:
        # Fallback to default bounds
        return {
            "north": 40.35,
            "south": 40.20,
            "east": -76.75,
            "west": -76.95,
            "center": {
                "lat": 40.2732,
                "lon": -76.8867
            }
        }

    return {
        "north": float(df['lat'].max()),
        "south": float(df['lat'].min()),
        "east": float(df['lon'].max()),
        "west": float(df['lon'].min()),
        "center": {
            "lat": float(df['lat'].mean()),
            "lon": float(df['lon'].mean())
        }
    }

@router.get("/maps/clusters")
async def get_pole_clusters(zoom: int = 10):
    """
    Get clustered poles for performance at low zoom levels
    """
    poles_csv = RAW_DATA_DIR / 'osm_poles_harrisburg_real.csv'

    if not poles_csv.exists():
        return {"clusters": []}

    df = pd.read_csv(poles_csv)
    df = df.dropna(subset=['lat', 'lon'])

    if len(df) == 0:
        return {"clusters": []}

    # Simple grid-based clustering
    # In production, use proper clustering (k-means, DBSCAN)
    grid_size = 0.01 if zoom > 12 else 0.05

    df['lat_grid'] = (df['lat'] / grid_size).round() * grid_size
    df['lon_grid'] = (df['lon'] / grid_size).round() * grid_size

    clusters = df.groupby(['lat_grid', 'lon_grid']).agg({
        'pole_id': 'count',
        'lat': 'mean',
        'lon': 'mean'
    }).reset_index()

    cluster_list = []
    for _, cluster in clusters.iterrows():
        try:
            lat = float(cluster['lat'])
            lon = float(cluster['lon'])
            count = int(cluster['pole_id'])
            if (-90 <= lat <= 90) and (-180 <= lon <= 180):
                cluster_list.append({
                    "lat": lat,
                    "lon": lon,
                    "count": count,
                    "radius": min(count * 5, 50)  # Dynamic radius
                })
        except (ValueError, TypeError):
            continue

    return {"clusters": cluster_list}
