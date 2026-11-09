"""Command-line inference using the author's trained model."""
import argparse
import json
from pathlib import Path

from common import MODEL, ROOT, CLASS_NAMES, CHINESE_NAMES
from advice import build_advice, advice_text


def main():
    parser = argparse.ArgumentParser(description='Local welding defect detection')
    parser.add_argument('image', help='Path to a JPG/PNG image')
    parser.add_argument('--conf', type=float, default=0.25)
    parser.add_argument('--output', default=str(ROOT / 'outputs'))
    args = parser.parse_args()
    from PIL import Image, ImageOps
    import torch
    from ultralytics import YOLO
    torch.set_num_threads(4)
    model = YOLO(str(MODEL))
    assert list(model.names.values()) == CLASS_NAMES, 'Unexpected checkpoint classes'
    image = ImageOps.exif_transpose(Image.open(args.image)).convert('RGB')
    result = model.predict(image, imgsz=640, conf=args.conf,
                           device=0 if torch.cuda.is_available() else 'cpu', verbose=False)[0]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    stem = Path(args.image).stem
    Image.fromarray(result.plot()[:, :, ::-1]).save(output / (stem + '-result.jpg'))
    detections = [{'class_id': int(b.cls.item()), 'class_name': model.names[int(b.cls.item())],
                   'class_name_zh': CHINESE_NAMES[int(b.cls.item())],
                   'confidence': float(b.conf.item()), 'xyxy': b.xyxy[0].cpu().tolist()}
                  for b in result.boxes]
    (output / (stem + '-result.json')).write_text(json.dumps(detections, ensure_ascii=False, indent=2), encoding='utf-8')
    advice = build_advice([d['class_id'] for d in detections])
    (output / (stem + '-advice.txt')).write_text(advice_text(advice), encoding='utf-8')
    (output / (stem + '-report.json')).write_text(json.dumps({
        'detections': detections, 'confidence_threshold': args.conf, 'advice': advice,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Detected {len(detections)} objects. Results saved to {output}')


if __name__ == '__main__':
    main()
