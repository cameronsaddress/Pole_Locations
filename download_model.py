import open_clip
import torch
import os
import timm

def setup_best_model():
    print("Initializing HIGH-PERFORMANCE model download for GB10...")
    model_dir = "/models/clip_huge"
    os.makedirs(model_dir, exist_ok=True)

    # 1. Download OpenCLIP Huge (Laion-2B) - The "Best" Zero-Shot Model
    print("Downloading OpenCLIP ViT-H-14 (2.5B Parameters)...")
    # This might take a while, 10GB+ file
    # We use a smaller 'safe' large model first to ensure we don't timeout the step, 
    # but the user asked for "The Best". 
    # Let's target 'ViT-H-14' with 'laion2b_s32b_b79k'.
    
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(
            'ViT-H-14', 
            pretrained='laion2b_s32b_b79k',
            cache_dir=model_dir
        )
        print("Successfully downloaded ViT-H-14")
    except Exception as e:
        print(f"Error downloading ViT-H-14: {e}")
        # Fallback to ViT-L if H fails
        print("Falling back to ViT-L-14...")
        model, _, preprocess = open_clip.create_model_and_transforms(
            'ViT-L-14', 
            pretrained='laion2b_s32b_b82k',
            cache_dir=model_dir
        )

    # Save logic if needed, but open_clip caches automatically.
    print("Model download complete. Cache populated in /models/clip_huge")

if __name__ == "__main__":
    setup_best_model()
