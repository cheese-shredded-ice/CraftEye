"""Local paths and display names shared by training and the UI."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / '.ultralytics'))
os.environ.setdefault('YOLO_AUTOINSTALL', 'false')
DATASET = ROOT / 'dataset'
MODEL = ROOT / 'models' / 'welding.pt'
CLASS_NAMES = ['Bad Weld', 'Good Weld', 'Defect']
CHINESE_NAMES = ['焊接不良', '焊接良好', '缺陷']
COLORS = ['#ef4444', '#16a34a', '#f59e0b']


def write_data_yaml():
    import yaml
    target = ROOT / 'data.local.yaml'
    target.write_text(yaml.safe_dump({
        'path': DATASET.as_posix(), 'train': 'train/images',
        'val': 'valid/images', 'test': 'test/images',
        'names': CLASS_NAMES,
    }, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return target
