
import argparse
import sys
import json
import logging
from pathlib import Path
import time

# Add project root
sys.path.append(str(Path(__file__).parent.parent.parent))

from ultralytics import YOLO
from src.config import PROCESSED_DATA_DIR, OUTPUTS_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def train_yolo(lr0, momentum, weight_decay, epochs, batch_size):
    """
    Run a single training trial with specific hyperparameters.
    """
    logger.info(f"Starting YOLO11l Training Trial. LR={lr0}, Mom={momentum}, WD={weight_decay}")
    
    # Check for dataset
    yaml_path = PROCESSED_DATA_DIR / 'pole_training_dataset' / 'dataset.yaml'
    if not yaml_path.exists():
        logger.error(f"Dataset not found at {yaml_path}")
        # Return dummy result if no data, to avoid crashing the whole loop
        print(json.dumps({"error": "Dataset missing", "map50": 0.0, "box_loss": 0.0}))
        return

    # Initialize model (YOLO11l)
    model = YOLO("yolo11l.pt") 
    
    # Project dir for this specific trial
    project_dir = OUTPUTS_DIR / "tuning_trials"
    run_name = f"trial_{int(time.time())}"
    
    # Define callback for live streaming
    def on_train_epoch_end(trainer):
        try:
            # Ultralytics V8/11 trainer object has these attributes
            # metrics keys usually: 'metrics/precision(B)', 'metrics/recall(B)', 'metrics/mAP50(B)', 'metrics/mAP50-95(B)'
            # val/box_loss, val/cls_loss, val/dfl_loss
            
            current_epoch = trainer.epoch + 1
            total_epochs = trainer.epochs
            
            # Use safe get
            map50 = trainer.metrics.get('metrics/mAP50(B)', 0.0)
            
            # Loss is tricky, it's often in trainer.loss_items (training loss) or trainer.metrics (val loss)
            # Let's take 'val/box_loss' if available, else 0
            box_loss = trainer.metrics.get('val/box_loss', 0.0)
            
            # Construct payload
            payload = {
                "type": "epoch",
                "epoch": current_epoch,
                "total_epochs": total_epochs,
                "map50": float(map50),
                "box_loss": float(box_loss),
                "gpu_mem": 0 # Placeholder or extract from torch.cuda.memory_reserved()
            }
            print(json.dumps(payload), flush=True)
            
        except Exception as e:
            # Fallback logging if structure changes
            print(json.dumps({"type": "log", "payload": f"Error in callback: {e}"}), flush=True)

    model.add_callback("on_train_epoch_end", on_train_epoch_end)

    def on_train_batch_end(trainer):
        # UI Visibility: Log progress every 10% of batches
        try:
            total = trainer.num_batches
            current = trainer.batch + 1
            if total > 0:
                interval = max(5, int(total * 0.1)) # At least every 5 batches
                if current % interval == 0 or current == 1:
                   print(json.dumps({
                       "type": "progress", 
                       "payload": f"Epoch {trainer.epoch + 1}/{trainer.epochs}: Batch {current}/{total}..."
                   }), flush=True)
        except:
            pass

    model.add_callback("on_train_batch_end", on_train_batch_end)

    try:
        results = model.train(
            data=str(yaml_path),
            epochs=epochs,
            batch=batch_size,
            lr0=lr0,
            momentum=momentum,
            weight_decay=weight_decay,
            project=str(project_dir),
            name=run_name,
            verbose=True
        )
        
        # Extract metrics
        # accessing results.box.map50 or similar
        # Ultralytics results object structure varies slightly by version
        # We'll try standard access patterns
        
        map50 = results.box.map50
        box_loss = results.box.loss_box if hasattr(results.box, 'loss_box') else 0.0
        # If missing, try to parse from csv
        
        metrics = {
            "map50": float(map50),
            "box_loss": float(box_loss) if box_loss is not None else 0.0,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Training failed: {e}")
        metrics = {
            "map50": 0.0, 
            "box_loss": 0.0,
            "error": str(e),
            "status": "failed"
        }

    # Print JSON to stdout for the backend to consume
    print(json.dumps(metrics))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lr0", type=float, default=0.01)
    parser.add_argument("--momentum", type=float, default=0.937)
    parser.add_argument("--weight_decay", type=float, default=0.0005)
    parser.add_argument("--epochs", type=int, default=50) # Keep low for tuning
    parser.add_argument("--batch", type=int, default=16)
    
    args = parser.parse_args()
    
    train_yolo(args.lr0, args.momentum, args.weight_decay, args.epochs, args.batch)
