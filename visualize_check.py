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

# Path# SATELLITE EXAMPLES
sat_examples = [
    "pole_116_SAT", "pole_117_SAT", "pole_124_SAT", "pole_134_SAT", "pole_142_SAT"
]
for ex in sat_examples:
    visualize(
        f"data/training/satellite_drops/images/{ex}.jpg", 
        f"data/training/satellite_drops/labels/{ex}.txt", 
        f"vis_manual_sat_{ex}.png"
    )

# STREET EXAMPLES
street_examples = [
    "pole_1004_view6_GSV", "pole_1037_view3_GSV", "pole_1037_view4_GSV", 
    "pole_1278_view3_GSV", "pole_1306_view5_GSV"
]
for ex in street_examples:
    visualize(
        f"data/training/layer1_drops/images/{ex}.jpg", 
        f"data/training/layer1_drops/labels/{ex}.txt", 
        f"vis_manual_street_{ex}.png"
    )
