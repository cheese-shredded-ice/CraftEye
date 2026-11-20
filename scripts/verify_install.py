"""Verify source integrity, dataset labels, inference, and held-out evaluation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from website.common import DATASET, MODEL, CLASS_NAMES, write_data_yaml
from download_dataset import matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--evaluate', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'verification.json')
    args = parser.parse_args()
    import torch
    import torchvision
    import ultralytics
    from PIL import Image
    from ultralytics import YOLO
    torch.set_num_threads(4)
    source = json.loads((ROOT / 'models' / 'source.json').read_text())
    assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == source['sha256']
    manifest = json.loads((ROOT / 'dataset-manifest.json').read_text())
    invalid = [e['path'] for e in manifest['files'] if not matches(DATASET / e['path'], e)]
    if invalid:
        raise RuntimeError(f'Missing or invalid source files ({len(invalid)}): {invalid[:5]}')
    counts, class_counts = {}, {}
    for split in ('train', 'valid', 'test'):
        images = sorted((DATASET / split / 'images').glob('*.jpg'))
        counts[split] = len(images)
        objects = Counter()
        for image in images:
            with Image.open(image) as opened:
                opened.verify()
            label = DATASET / split / 'labels' / (image.stem + '.txt')
            for line in label.read_text().splitlines():
                values = list(map(float, line.split()))
                assert len(values) == 5, str(label)
                cls, x, y, w, h = values
                assert cls in (0, 1, 2) and all(0 <= v <= 1 for v in values[1:]), str(label)
                assert w > 0 and h > 0, str(label)
                objects[CLASS_NAMES[int(cls)]] += 1
        class_counts[split] = dict(objects)
    model = YOLO(str(MODEL))
    assert list(model.names.values()) == CLASS_NAMES
    device = 0 if torch.cuda.is_available() else 'cpu'
    sample = next((DATASET / 'test' / 'images').glob('*.jpg'))
    result = model.predict(Image.open(sample).convert('RGB'), imgsz=640, device=device, verbose=False)[0]
    output = ROOT / 'outputs'
    output.mkdir(exist_ok=True)
    Image.fromarray(result.plot()[:, :, ::-1]).save(output / 'verification-result.jpg')
    report = {'python': sys.version, 'torch': torch.__version__, 'torchvision': torchvision.__version__,
              'ultralytics': ultralytics.__version__, 'device': device,
              'source_files_verified': len(manifest['files']), 'images': counts,
              'annotations': class_counts, 'classes': model.names,
              'sample_detections': len(result.boxes), 'model_sha256_verified': True}
    if args.evaluate:
        metrics = model.val(data=str(write_data_yaml()), split='test', imgsz=640,
                            batch=4, device=device, workers=0, plots=False,
                            project=str(ROOT / 'outputs'), name='test-evaluation', exist_ok=True)
        metrics_report = {'model_source': source['repo'], 'test_images': counts['test'],
                          'precision': float(metrics.box.mp), 'recall': float(metrics.box.mr),
                          'mAP50': float(metrics.box.map50), 'mAP50_95': float(metrics.box.map),
                          'per_class_mAP50_95': [float(v) for v in metrics.box.maps]}
        (ROOT / 'models' / 'metrics.json').write_text(json.dumps(metrics_report, indent=2), encoding='utf-8')
        report['test_metrics'] = metrics_report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
