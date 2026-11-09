"""Download the author's trained checkpoint and verify its SHA256."""
import hashlib
import json
from pathlib import Path
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = 'avinashhm/welding-defect-yolov8-full-training'
REVISION = '2cbc6dc08b74b6bab1ebafc59a3804e4bc43e517'
SHA256 = '92243d6d3b3c667f0dd8f2d2261d480c744912e97e1842e9b92dc9465de52c86'


def main():
    dest = ROOT / 'models'
    dest.mkdir(exist_ok=True)
    target = dest / 'welding.pt'
    if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != SHA256:
        url = f'https://huggingface.co/{REPO}/resolve/{REVISION}/weights/best.pt'
        for attempt in range(5):
            try:
                temp = target.with_suffix('.part')
                with urllib.request.urlopen(url, timeout=90) as response, temp.open('wb') as out:
                    while chunk := response.read(1024 * 1024):
                        out.write(chunk)
                if hashlib.sha256(temp.read_bytes()).hexdigest() != SHA256:
                    raise ValueError('Model SHA256 mismatch')
                temp.replace(target)
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 ** attempt)
    (dest / 'source.json').write_text(json.dumps({
        'repo': REPO, 'revision': REVISION, 'file': 'weights/best.pt',
        'sha256': SHA256, 'local_file': 'models/welding.pt',
        'author_reported_epochs': 100, 'imgsz': 640, 'trained_locally': False,
    }, indent=2), encoding='utf-8')
    for filename in ('README.md', 'args.yaml', 'results.csv'):
        try:
            with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{filename}', timeout=60) as response:
                (dest / ('author-' + filename)).write_bytes(response.read())
        except Exception as exc:
            print(f'Optional documentation download failed: {filename}: {exc}', flush=True)
    print(f'Author checkpoint downloaded and SHA256 verified: {target}', flush=True)


if __name__ == '__main__':
    main()
