"""Shared, serialized model inference for uploads and camera workers."""
import threading

from PIL import ImageDraw, ImageFont
import streamlit as st

from common import MODEL, CHINESE_NAMES, COLORS


def draw_boxes(image, boxes):
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', max(14, image.width // 45))
    except OSError:
        font = ImageFont.load_default()
    for cls, coords, confidence in boxes:
        color = COLORS[cls]
        draw.rectangle(coords, outline=color, width=max(2, image.width // 200))
        label = CHINESE_NAMES[cls] + (f' {confidence:.0%}' if confidence is not None else '')
        x, y = coords[:2]
        y = max(0, y - 24)
        rect = draw.textbbox((x, y), label, font=font)
        draw.rectangle(rect, fill=color)
        draw.text((x, y), label, fill='white', font=font)
    return canvas


class ModelRunner:
    def __init__(self, path):
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(4)
        self.model = YOLO(path)
        self.device = 0 if torch.cuda.is_available() else 'cpu'
        self.lock = threading.Lock()

    def infer(self, image, confidence):
        # Ultralytics caches mutable predictor state; serialize uploads and streams.
        with self.lock:
            result = self.model.predict(image, conf=confidence, imgsz=640,
                                        device=self.device, verbose=False)[0]
            boxes, rows = [], []
            for box in result.boxes:
                cls = int(box.cls.item())
                score = float(box.conf.item())
                coords = box.xyxy[0].cpu().tolist()
                boxes.append((cls, coords, score))
                rows.append({'类别': CHINESE_NAMES[cls], '置信度': round(score, 4),
                             '左': round(coords[0]), '上': round(coords[1]),
                             '右': round(coords[2]), '下': round(coords[3])})
        return draw_boxes(image, boxes), rows


@st.cache_resource
def load_runner(path, modified):
    return ModelRunner(path)


def get_runner():
    return load_runner(str(MODEL), MODEL.stat().st_mtime_ns)


def infer(image, confidence):
    return get_runner().infer(image, confidence)
