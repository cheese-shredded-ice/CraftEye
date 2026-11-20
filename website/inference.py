"""Shared, serialized model inference for uploads and camera workers."""
import threading
import math

from PIL import ImageDraw, ImageFont
import streamlit as st

from .common import MODEL, CLASS_NAMES, CHINESE_NAMES, COLORS


def read_annotation(label, size):
    """Parse normalized YOLO boxes; never draw corrupt labels as ground truth."""
    boxes, rows = [], []
    width, height = size
    for line in label.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip():
            continue
        cls, x, y, w, h = map(float, line.split())
        if (not cls.is_integer() or not 0 <= cls < len(CLASS_NAMES)
                or not all(math.isfinite(v) and 0 <= v <= 1 for v in (x, y, w, h))
                or min(w, h) == 0):
            raise ValueError('标注类别或坐标无效')
        cls = int(cls)
        coords = ((x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height)
        boxes.append((cls, coords, None))
        rows.append({'类别': CHINESE_NAMES[cls], '原始标签': CLASS_NAMES[cls]})
    return boxes, rows


def draw_boxes(image, boxes):
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    try:
        # The annotated image is also used in the presentation view, so keep the
        # class name readable at a distance.  Detection confidence remains in
        # ``rows`` for filtering and reports; it is intentionally omitted from
        # the visual label to keep the overlay concise.
        # The result image is fit to the workbench column in the browser. Use a
        # large source label so the class name remains readable after that fit.
        font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', max(30, image.width // 16))
    except OSError:
        font = ImageFont.load_default()
    padding = max(3, image.width // 320)
    for cls, coords, confidence in boxes:
        color = COLORS[cls]
        draw.rectangle(coords, outline=color, width=max(2, image.width // 200))
        label = CHINESE_NAMES[cls]
        x, y = coords[:2]
        text_box = draw.textbbox((0, 0), label, font=font)
        label_width = text_box[2] - text_box[0]
        label_height = text_box[3] - text_box[1]
        # Keep the enlarged label fully visible even when the detection box is
        # close to the right edge of a narrow source image.
        label_x = min(max(0, int(x)), max(0, image.width - label_width - padding * 2))
        label_y = max(0, y - label_height - padding * 2)
        rect = (label_x, label_y, label_x + label_width + padding * 2,
                label_y + label_height + padding * 2)
        draw.rectangle(rect, fill=color)
        draw.text((label_x + padding, label_y + padding), label, fill='white', font=font)
    return canvas


class ModelRunner:
    def __init__(self, path):
        self.lock = threading.Lock()
        self.onnx = str(path).lower().endswith('.onnx')
        if self.onnx:
            from .onnx_backend import ONNXDetector
            self.model = ONNXDetector(path)
            self.device = 'cpu'
            return
        import torch
        from ultralytics import YOLO
        torch.set_num_threads(4)
        self.model = YOLO(path)
        self.device = 0 if torch.cuda.is_available() else 'cpu'

    def infer(self, image, confidence):
        # Ultralytics caches mutable predictor state; serialize uploads and streams.
        with self.lock:
            if self.onnx:
                boxes = self.model.detect(image, confidence)
                rows = [{'类别': CHINESE_NAMES[cls], '置信度': round(score, 4),
                         '左': round(coords[0]), '上': round(coords[1]),
                         '右': round(coords[2]), '下': round(coords[3])}
                        for cls, coords, score in boxes]
                return draw_boxes(image, boxes), rows
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
