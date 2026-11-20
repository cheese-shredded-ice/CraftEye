"""Select YOLO regions for closer visual inspection, retaining nested small defects."""
import math

FOCUS_CONFIDENCE = 0.60
MAX_FOCUS_CROPS = 8


def focus_regions(rows, size):
    width, height = size
    candidates = []
    seen = set()
    priority = {'缺陷': 0, '焊接不良': 1, '焊接良好': 2}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        values = [row.get(key) for key in ('置信度', '左', '上', '右', '下')]
        if any(type(value) not in (float, int) or not math.isfinite(value) for value in values):
            continue
        confidence, left, top, right, bottom = values
        if not FOCUS_CONFIDENCE < confidence <= 1:
            continue
        left, top = max(0, math.floor(left)), max(0, math.floor(top))
        right, bottom = min(width, math.ceil(right)), min(height, math.ceil(bottom))
        if right <= left or bottom <= top:
            continue
        label = row.get('类别')
        if label not in priority:
            continue
        identity = (label, left, top, right, bottom)
        if identity in seen:
            continue
        seen.add(identity)
        pad_x, pad_y = max(8, round((right-left)*0.12)), max(8, round((bottom-top)*0.12))
        candidates.append({'detection_index': index, 'label': label, 'confidence': confidence,
            'box': [left, top, right, bottom],
            'crop_box': [max(0, left-pad_x), max(0, top-pad_y), min(width, right+pad_x), min(height, bottom+pad_y)]})
    # Do not apply overlap suppression: a small defect inside a bad-weld box is useful.
    candidates.sort(key=lambda region: (priority[region['label']], -region['confidence'], region['detection_index']))
    return candidates
