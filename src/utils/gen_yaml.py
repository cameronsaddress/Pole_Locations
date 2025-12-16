
import yaml
import os
from pathlib import Path

data = {
    'path': '/workspace/data/training/unified_dataset',
    'train': 'images/train',
    'val': 'images/val',
    'nc': 1,
    'names': ['utility_pole']
}

Path('/workspace/data/training/unified_dataset').mkdir(parents=True, exist_ok=True)
with open('/workspace/data/training/unified_dataset/dataset.yaml', 'w') as f:
    yaml.dump(data, f)
print("YAML Generated.")
