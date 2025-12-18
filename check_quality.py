
import os
from PIL import Image, ImageDraw

def create_preview(image_id, base_dir, out_dir):
    img_path = os.path.join(base_dir, "images", f"{image_id}.jpg")
    
    if not os.path.exists(img_path):
        print(f"Missing {image_id}")
        return

    # Load Image
    img = Image.open(img_path)
    
    # Save
    out_path = os.path.join(out_dir, f"check_{image_id}.png")
    img.save(out_path)
    print(f"Created {out_path}")

base = "/home/canderson/PoleLocations/data/training/satellite_drops"
out = "/home/canderson/PoleLocations"
create_preview("pole_187_SAT", base, out)
