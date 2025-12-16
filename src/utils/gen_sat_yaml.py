
import yaml
from pathlib import Path
import os

# Create dir if not exists (for sat expert)
Path('/workspace/data/training/satellite_expert').mkdir(parents=True, exist_ok=True)

data = {
    'path': '/workspace/data/training/satellite_expert',
    'train': 'images/train', 
    'val': 'images/val', 
    'nc': 1,
    'names': ['utility_pole']
}

with open('/workspace/data/training/satellite_expert/dataset.yaml', 'w') as f:
    yaml.dump(data, f)

print("YAML Generated.")
