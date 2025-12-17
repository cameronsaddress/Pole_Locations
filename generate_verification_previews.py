
import os
from PIL import Image, ImageDraw

def create_preview(image_id, base_dir, out_dir):
    img_path = os.path.join(base_dir, "images", f"{image_id}.jpg")
    lbl_path = os.path.join(base_dir, "labels", f"{image_id}.txt")
    
    if not os.path.exists(img_path) or not os.path.exists(lbl_path):
        print(f"Missing {image_id}")
        return

    # Load Image
    img = Image.open(img_path)
    w, h = img.size
    draw = ImageDraw.Draw(img)
    
    # Load Label
    with open(lbl_path, "r") as f:
        line = f.readline().strip()
        parts = list(map(float, line.split()))
        # class x y w h
        cls, x, y, bw, bh = parts
        
        # Denormalize
        px = x * w
        py = y * h
        
        # Draw Red Dot (Radius 3)
        r = 3
        draw.ellipse((px-r, py-r, px+r, py+r), fill="red", outline="red")
        
    # Save
    out_path = os.path.join(out_dir, f"preview_{image_id}.png")
    img.save(out_path)
    print(f"Created {out_path}")

base = "/home/canderson/PoleLocations/data/training/satellite_drops"
out = "/home/canderson/PoleLocations"
create_preview("pole_582_SAT", base, out)
create_preview("pole_800_SAT", base, out)
