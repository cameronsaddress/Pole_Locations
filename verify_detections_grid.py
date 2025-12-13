
import logging
from pathlib import Path
import random
import sys
from shapely.wkt import loads
import rasterio
from rasterio.windows import Window
import matplotlib.pyplot as plt
import numpy as np
from sqlalchemy import text
from sqlmodel import Session

# Add project root to path
sys.path.append("/workspace")
sys.path.append("/workspace/backend-enterprise")

from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_verification_grid():
    logger.info("Fetching recent high-confidence detections for verification...")
    
    with Session(engine) as session:
        # Get top 5 highest confidence detections
        query = text("""
            SELECT image_path, ST_AsText(location) as loc_wkt, confidence, road_distance_m, height_ag_m, class_name
            FROM detections 
            ORDER BY confidence DESC 
            LIMIT 5
        """)
        results = session.execute(query).fetchall()
        
    if not results:
        logger.error("No detections found!")
        return

    # Use top 5 results directly
    # random.shuffle(results) - Removed to show best candidates
    
    fig, axes = plt.subplots(1, 5, figsize=(20, 5))
    
    plot_idx = 0
    
    for candidate in results:
        if plot_idx >= 5:
            break
            
        image_path, loc_wkt, conf, rd_dist, hag, class_name = candidate
        
        try:
            pt = loads(loc_wkt)
            lon, lat = pt.x, pt.y
            
            # NOTE: DB coordinates are treated as aligned with imagery (no offset validation applied here)
            
            with rasterio.open(image_path) as src:
                # Transform lat/lon to pixel coords
                if src.crs and src.crs.to_string() != "EPSG:4326":
                    from rasterio.warp import transform
                    new_x, new_y = transform("EPSG:4326", src.crs, [lon], [lat])
                    col, row = src.index(new_x[0], new_y[0])
                else:
                    col, row = src.index(lon, lat)
                
                # Check Bounds
                if not (0 <= col < src.width and 0 <= row < src.height):
                    logger.warning(f"Skipping OOB Detection: {loc_wkt} in {Path(image_path).name} (Px: {col},{row})")
                    continue

                # Crop 256x256
                size = 256
                window = Window(col - size//2, row - size//2, size, size)
                
                data = src.read([1, 2, 3], window=window)
                
                # Handle edge cases
                if data.shape[1] != size or data.shape[2] != size:
                    padded = np.zeros((3, size, size), dtype=data.dtype)
                    padded[:, :data.shape[1], :data.shape[2]] = data
                    data = padded
                    
                img = np.transpose(data, (1, 2, 0))
                
                # Check for empty/black image
                if img.mean() < 5.0:
                    logger.warning(f"Skipping Black Image: Mean={img.mean():.1f}")
                    continue
                
                # Debug Info
                logger.info(f"Sample {plot_idx}: Path={Path(image_path).name}, Geo=({lon:.5f}, {lat:.5f}), Px=({col}, {row}), Size={src.width}x{src.height}, Mean={img.mean():.1f}")
                
                ax = axes[plot_idx]
                ax.imshow(img)
                hag_str = f"{hag:.1f}m" if hag is not None else "?"
                rd_str = f"{rd_dist:.1f}m" if rd_dist is not None else "?"
                cls_short = class_name.replace("pole_", "").capitalize() if class_name else "Unk"
                
                ax.set_title(f"{cls_short}\nConf: {conf:.2f}\nRd: {rd_str}", fontsize=9)
                ax.axis('off')
                
                # Draw small circle at center
                ax.plot(size//2, size//2, 'r+', markersize=10)
                
                plot_idx += 1
                
        except Exception as e:
            logger.error(f"Failed to extract candidate: {e}")
            continue

    # Hide unused axes if < 5 found
    for j in range(plot_idx, 5):
        axes[j].axis('off')

    output_path = "/workspace/latest_detections_grid.png"
    plt.tight_layout()
    plt.savefig(output_path)
    logger.info(f"✅ Saved verification grid to {output_path}")

if __name__ == "__main__":
    generate_verification_grid()
