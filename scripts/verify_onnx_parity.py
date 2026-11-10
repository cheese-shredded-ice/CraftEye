"""Compare portable inference with the current PyTorch model on held-out images."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common import DATASET
from onnx_backend import ONNXDetector, preprocess, postprocess
import torch
from ultralytics import YOLO

torch.set_num_threads(4)
original=YOLO(str(ROOT/'models/welding.pt'))
portable=ONNXDetector(ROOT/'models/welding.onnx')
samples=sorted((DATASET/'test/images').glob('*.jpg'))
worst_box=worst_score=0.0
checks=objects=0
started=time.monotonic()
for index,sample in enumerate(samples):
    image=Image.open(sample).convert('RGB')
    thresholds=[.05,.25,.6,.95] if index<8 else [.25]
    tensor=preprocess(image)
    output=portable.session.run(None,{portable.input_name:tensor})[0]
    for threshold in thresholds:
        baseline=original.predict(image,conf=threshold,imgsz=640,device='cpu',verbose=False)[0]
        expected=[(int(b.cls.item()),b.xyxy[0].tolist(),float(b.conf.item())) for b in baseline.boxes]
        actual=postprocess(output,tensor.shape[2:],image.size,threshold)
        assert len(actual)==len(expected),(sample.name,threshold,len(expected),len(actual))
        pending=list(actual)
        for cls,coords,confidence in expected:
            candidates=[(i,b) for i,b in enumerate(pending) if b[0]==cls]
            assert candidates,(sample.name,cls,pending)
            best,box=min(candidates,key=lambda pair:np.abs(np.asarray(pair[1][1])-coords).max())
            difference=float(np.abs(np.asarray(box[1])-coords).max())
            score_diff=abs(box[2]-confidence)
            assert difference<.15,(sample.name,difference,coords,box)
            assert score_diff<.0001,(sample.name,score_diff)
            worst_box=max(worst_box,difference)
            worst_score=max(worst_score,score_diff)
            objects+=1
            pending.pop(best)
        checks+=1
    if (index+1)%25==0:print(f'Compared {index+1}/{len(samples)} images',flush=True)
summary={'images':len(samples),'threshold_checks':checks,'matched_detections':objects,
         'max_box_difference_pixels':worst_box,'max_confidence_difference':worst_score,
         'seconds':round(time.monotonic()-started,1),'all_detection_counts_and_classes_match':True}
folder=ROOT/'outputs/portable-lite-check'
folder.mkdir(exist_ok=True)
(folder/'model-parity.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
