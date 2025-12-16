# Implementation Plan - Smart Mining & Satellite Verification

This plan outlines the steps to verify utility pole locations in satellite imagery using Grounding DINO (Zero-Shot Detection) before committing to a full training run.

## User Objective
- Verify satellite imagery contains valid poles (not just grass/roads).
- Use "Elite" tools (Grounding DINO) to identify poles ~without~ training first.
- Utilize the available DGX GPU (128GB VRAM).

## Steps

### 1. Environment Verification (Complete)
- [x] Check `polevision-gpu` container status.
- [x] Verify CUDA availability (`torch.cuda.is_available()`). -> **Confirmed: NVIDIA GB10 Detected**.

### 2. Smart Miner Deployment
- [ ] Install necessary dependencies (`autodistill`, `roboflow`, `groundingdino`) in the container. (Partially Done).
- [ ] Create `src/training/smart_miner_autodistill.py` with:
    - Efficient Tiling (Zoom 19).
    - Grounding DINO Inference.
    - Annotation (Bounding Box + Confidence).
    - Output to `frontend-enterprise/public` for instant review.

### 3. Execution & Monitoring
- [ ] Run the Smart Miner on a sample of 5-10 poles.
- [ ] Monitor GPU usage (expect spikes during inference).
- [ ] Check for "empty" or "hallucinated" detections.

### 4. User Review
- [ ] Present `smart_check_{i}.jpg` images to the user.
- [ ] If successful, approve the "Full Grid Mining" of 3,000+ poles using this verified method.

## Protocol Compliance
- Running inside `polevision-gpu`.
- Using Absolute Paths.
- No sudo.
