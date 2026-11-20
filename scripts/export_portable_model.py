"""Export the existing trained model without retraining or quantization."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from website import common  # Sets YOLO_AUTOINSTALL=false before importing Ultralytics.
import torch
from ultralytics import YOLO

torch.set_num_threads(4)
if __name__=='__main__':
    YOLO(str(ROOT/'models/welding.pt')).export(format='onnx',imgsz=640,opset=17,
        dynamic=True,simplify=False,half=False,nms=False,device='cpu')
