"""Compare the author's ONNX model with PyTorch; write a Java decoder fixture."""
import json
from pathlib import Path
import sys

import cv2
import numpy as np
import onnxruntime as ort
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from website.common import MODEL
from ultralytics import YOLO
from ultralytics.utils.nms import non_max_suppression


def main():
    torch.set_num_threads(4)
    options=ort.SessionOptions()
    options.intra_op_num_threads=4
    session=ort.InferenceSession(str(ROOT/'android/app/src/main/assets/welding.onnx'), sess_options=options,providers=['CPUExecutionProvider'])
    model=YOLO(str(MODEL))
    samples=[ROOT/'android/app/src/main/assets/sample.jpg']
    for label in (ROOT/'dataset/test/labels').glob('*.txt'):
        if label.read_text().startswith('1 '):
            samples.append(ROOT/'dataset/test/images'/ (label.stem+'.jpg'));break
    reports=[]
    for sample in samples:
        image=cv2.imdecode(np.fromfile(sample,dtype=np.uint8),cv2.IMREAD_COLOR)
        h,w=image.shape[:2];scale=min(640/w,640/h)
        nw,nh=round(w*scale),round(h*scale);left,top=(640-nw)//2,(640-nh)//2
        padded=np.full((640,640,3),114,dtype=np.uint8)
        padded[top:top+nh,left:left+nw]=cv2.resize(image,(nw,nh))
        tensor=np.ascontiguousarray(padded[:,:,::-1].transpose(2,0,1)[None],dtype=np.float32)/255
        output=session.run(None,{'images':tensor})[0]
        decoded=non_max_suppression(torch.from_numpy(output.copy()),conf_thres=0.25,iou_thres=0.7)[0].numpy()
        decoded[:,[0,2]]=(decoded[:,[0,2]]-left)/(nw/w)
        decoded[:,[1,3]]=(decoded[:,[1,3]]-top)/(nh/h)
        decoded[:,[0,2]]=decoded[:,[0,2]].clip(0,w)
        decoded[:,[1,3]]=decoded[:,[1,3]].clip(0,h)
        reference=model.predict(image,conf=0.25,iou=0.7,imgsz=640,rect=False,device='cpu',verbose=False)[0].boxes.data.numpy()
        assert decoded.shape==reference.shape,(decoded,reference)
        assert np.array_equal(decoded[:,5],reference[:,5])
        assert np.max(np.abs(decoded[:,4]-reference[:,4]),initial=0)<0.002
        assert np.max(np.abs(decoded[:,:4]-reference[:,:4]),initial=0)<2
        reports.append({'sample':sample.name,'detections':len(decoded),'max_score_delta':float(np.max(np.abs(decoded[:,4]-reference[:,4]),initial=0)),
                        'max_box_delta_pixels':float(np.max(np.abs(decoded[:,:4]-reference[:,:4]),initial=0))})
        if sample==samples[0]:
            fixtures=ROOT/'android/app/src/test/resources';fixtures.mkdir(parents=True,exist_ok=True)
            output.astype('>f4').tofile(fixtures/'model-output.bin')
            expected='\n'.join(','.join(map(str,row)) for row in decoded)
            (fixtures/'expected-boxes.csv').write_text(expected,encoding='ascii')
            (fixtures/'geometry.txt').write_text(f'{w},{h},{nw/w},{nh/h},{left},{top}',encoding='ascii')
    (ROOT/'android/model-verification.json').write_text(json.dumps({'input_shape':[1,3,640,640],'output_shape':[1,7,8400],'comparisons':reports},indent=2),encoding='utf-8')
    print(json.dumps(reports,indent=2))


if __name__=='__main__':main()
