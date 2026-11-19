"""Local open-source YOLO models for workshop behaviour (no cloud calls)."""
from pathlib import Path
import threading
import time

from PIL import Image, ImageDraw, ImageFont

MODEL_DIR = Path(__file__).parent / 'models' / 'behavior'
MODEL_FILES = ('yolo11n-pose.pt', 'welding-ppe.pt', 'yolo11n.pt')
_runner = None
_load_lock = threading.Lock()
PPE_NAMES = {'avec_casque': '面罩', 'sans_casque': '未戴面罩线索', 'avec_gants': '手套',
             'sans_gants': '未戴手套线索', 'tablier_ferme': '围裙', 'sans_tablier': '未穿围裙线索',
             'tablier_ouvert': '围裙敞开', 'chaussure_adequat': '鞋类', 'chaussure_inadequat': '鞋类异常线索',
             'presence_accessoires': '饰品线索', 'presence_cheveux': '头发线索'}
SKELETON = ((5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12),
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16))


def missing_models():
    return [name for name in MODEL_FILES if not (MODEL_DIR / name).is_file()]


class BehaviorRunner:
    def __init__(self):
        missing = missing_models()
        if missing:
            raise FileNotFoundError('行为模型尚未安装：' + '、'.join(missing))
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(4)
        self.pose = YOLO(str(MODEL_DIR / MODEL_FILES[0]))
        self.ppe = YOLO(str(MODEL_DIR / MODEL_FILES[1]))
        self.objects = YOLO(str(MODEL_DIR / MODEL_FILES[2]))
        self.lock = threading.Lock()

    def detect(self, image):
        started = time.monotonic()
        with self.lock:
            pose = self.pose.predict(image, imgsz=640, conf=.35, device='cpu', verbose=False)[0]
            ppe = self.ppe.predict(image, imgsz=640, conf=.25, device='cpu', verbose=False)[0]
            objects = self.objects.predict(image, imgsz=640, conf=.5, classes=[67], device='cpu', verbose=False)[0]
            people = []
            for box, points in zip(pose.boxes, pose.keypoints.data):
                people.append({'box': box.xyxy[0].cpu().tolist(), 'confidence': float(box.conf.item()),
                               'points': points.cpu().tolist()})
            equipment = [{'box': b.xyxy[0].cpu().tolist(), 'confidence': float(b.conf.item()),
                          'class': self.ppe.names[int(b.cls.item())]} for b in ppe.boxes]
            phones = [{'box': b.xyxy[0].cpu().tolist(), 'confidence': float(b.conf.item()),
                       'class': 'cell phone'} for b in objects.boxes]
        return {'people': people, 'equipment': equipment, 'phones': phones,
                'elapsed_ms': round((time.monotonic()-started)*1000, 1)}


def get_behavior_runner():
    global _runner
    with _load_lock:
        if _runner is None:
            _runner = BehaviorRunner()
    return _runner


def annotate(image, detections, report):
    out = image.copy()
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', max(13, image.width//40))
    except OSError:
        font = ImageFont.load_default()
    roi = report['config']['roi']
    draw.rectangle((roi[0]*out.width, roi[1]*out.height, roi[2]*out.width, roi[3]*out.height), outline='#22d3ee', width=2)
    for person in detections['people']:
        draw.rectangle(person['box'], outline='#22c55e', width=2)
        pts = person['points']
        for a, b in SKELETON:
            if min(pts[a][2], pts[b][2]) >= report['config']['keypoint_threshold']:
                draw.line((pts[a][0], pts[a][1], pts[b][0], pts[b][1]), fill='#22d3ee', width=3)
    for item in detections['equipment'] + detections['phones']:
        if item['confidence'] < report['config']['ppe_threshold']:
            continue
        x1, y1, x2, y2 = item['box']
        color = '#fb923c' if item['class'].startswith(('sans_', 'presence_')) else '#eab308'
        label = PPE_NAMES.get(item['class'], '手机') + f" {item['confidence']:.0%}"
        draw.rectangle(item['box'], outline=color, width=2)
        y = max(0, y1-20)
        draw.rectangle(draw.textbbox((x1, y), label, font=font), fill='#102539')
        draw.text((x1, y), label, fill=color, font=font)
    current = report['latest'] or {}
    status = {'inside': '工位区域内', 'outside': '工位区域外', 'unknown': '暂无法判断'}.get(current.get('location'), '等待画面')
    label = status + (f" · 躯干 {current['angle']:.0f}°" if current.get('angle') is not None else '')
    draw.rectangle(draw.textbbox((6, 6), label, font=font), fill='#102539')
    draw.text((6, 6), label, fill='white', font=font)
    return out
