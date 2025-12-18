import os
from PIL import Image, ImageDraw

def visualize(image_path, label_path, output_path):
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return
        
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)
    width, height = img.size
    
    if os.path.exists(label_path):
        with open(label_path, 'r') as f:
            lines = f.readlines()
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 5:
                    cls, x, y, w, h = map(float, parts[:5])
                    
                    px = x * width
                    py = y * height
                    pw = w * width
                    ph = h * height
                    
                    # Draw Box (Green)
                    x1 = px - pw/2
                    y1 = py - ph/2
                    x2 = px + pw/2
                    y2 = py + ph/2
                    draw.rectangle((x1, y1, x2, y2), outline="lime", width=2)
                    
                    # Draw Center Dot (Red)
                    r = 3
                    draw.ellipse((px-r, py-r, px+r, py+r), fill="red", outline="black")
    
    img.save(output_path)
    print(f"Saved {output_path}")

# Paths
base_img = "/home/canderson/PoleLocations/data/training/satellite_drops/images"
base_lbl = "/home/canderson/PoleLocations/data/training/satellite_drops/labels"

visualize(f"{base_img}/pole_481_SAT.jpg", f"{base_lbl}/pole_481_SAT.txt", "vis_pole_481_gemini25.png")
