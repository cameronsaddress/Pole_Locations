import os
import sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.windows import Window
from sqlalchemy import create_engine, text
from PIL import Image, ImageDraw
from pyproj import Transformer

# Path config (Inside Docker)
PROJECT_ROOT = Path("/workspace")
DB_URL = os.getenv("DATABASE_URL", "postgresql://pole_user:pole_secure_password@localhost:5432/polevision")

def main():
    print(f"Connecting to DB: {DB_URL}")
    engine = create_engine(DB_URL)
    
    # Get top 16 high confidence detections (valid utility poles)
    # We purposefully exclude 'pole_damage' etc just to show the main 'utility_pole' ones first, 
    # but let's just show everything with high confidence.
    query = """
    SELECT image_path, ST_X(location::geometry) as lon, ST_Y(location::geometry) as lat, confidence, class_name
    FROM detections
    WHERE confidence > 0.4
    ORDER BY confidence DESC
    LIMIT 16;
    """
    
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(query)).fetchall()
    except Exception as e:
        print(f"DB Error: {e}")
        return

    print(f"Found {len(rows)} high-confidence detections.")
    
    crops = []
    
    for row in rows:
        docker_path = row[0]
        lon = row[1]
        lat = row[2]
        conf = row[3]
        cls_name = row[4]
        
        # The path in DB is already /workspace/... so we use it directly
        local_path = Path(docker_path)
        
        if not local_path.exists():
            print(f"Missing file: {local_path}")
            continue
            
        try:
            with rasterio.open(local_path) as src:
                # Convert lat/lon to pixel
                # Assume WGS84 for database points
                transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                xx, yy = transformer.transform(lon, lat)
                
                row_px, col_px = src.index(xx, yy)
                
                # Crop
                N = 100 # 200x200 pixel crop
                window = Window(col_px - N, row_px - N, N*2, N*2)
                
                # Read
                rgb = src.read([1, 2, 3], window=window)
                
                # Transpose to HWC
                img_data = np.transpose(rgb, (1, 2, 0))
                
                # Convert to PIL
                # Check data type
                if img_data.dtype != np.uint8:
                     # Normalize if needed, usually NAIP is uint8
                     pass

                pil_img = Image.fromarray(img_data)
                
                # Draw Box (the pole is in the center)
                draw = ImageDraw.Draw(pil_img)
                # Center is N, N
                r = 20
                # Draw red circle around the pole location
                draw.ellipse((N-r, N-r, N+r, N+r), outline="red", width=3)
                
                # Text
                draw.text((5, 5), f"Conf: {conf:.2f}", fill="yellow")
                draw.text((5, 15), f"{cls_name}", fill="yellow")
                
                crops.append(pil_img)
                print(f"Generated crop for pole at {lat:.5f}, {lon:.5f}")
                
        except Exception as e:
            print(f"Error processing {local_path}: {e}")
            
    # Combine into grid (4x4)
    if not crops:
        print("No crops generated.")
        return

    w, h = crops[0].size
    grid_w = w * 4
    grid_h = h * 4
    grid_img = Image.new('RGB', (grid_w, grid_h))
    
    for i, crop in enumerate(crops):
        if i >= 16: break
        r = i // 4
        c = i % 4
        grid_img.paste(crop, (c*w, r*h))
        
    out_path = PROJECT_ROOT / "proof_of_poles_real.jpg"
    grid_img.save(out_path)
    print(f"Proof saved to {out_path}")

if __name__ == "__main__":
    main()
