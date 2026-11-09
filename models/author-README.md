
---
library_name: ultralytics
tags:
  - object-detection
  - yolov8
  - welding-defect
  - industrial-inspection
---

# Welding Defect Detection Model (YOLOv8)

This is a fine-tuned YOLOv8 model for detecting welding defects such as:

- Good Weld
- Bad Weld
- Defect

Includes full training artifacts:
- Best model weights (`best.pt`)
- Final model weights (`last.pt`)
- Training logs
- Validation predictions
- Augmented training batches

## Training Details

- Model Type: YOLOv8
- Dataset: The Welding Defect Dataset - v2
- Classes: 3
- Epochs: 100
- Image Size: 640x640
- Batch Size: 16

## Usage

```python
from ultralytics import YOLO

model = YOLO("YOUR_HF_USERNAME/welding-defect-yolov8-full-training")
results = model("image.jpg")
results[0].show()
