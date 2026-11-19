"""Fetch verified open-source weights and optional local test videos."""
import argparse
import hashlib
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--videos', action='store_true', help='Also download local test videos.')
    args = parser.parse_args()
    resources = json.loads((ROOT/'assets/behavior/resources.json').read_text(encoding='utf-8'))
    for resource in resources:
        if resource['role'] == 'test video' and not args.videos:
            continue
        path = ROOT/resource['path']
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == resource['sha256']:
            print('Verified:', path.name, flush=True)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix+'.download')
        try:
            with requests.get(resource['url'], headers={'User-Agent':'CraftEyeDevelopment/1.0'}, stream=True, timeout=(15, 90)) as response:
                response.raise_for_status()
                with temporary.open('wb') as output:
                    for chunk in response.iter_content(1024*1024):
                        output.write(chunk)
            digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
            if digest != resource['sha256']:
                raise RuntimeError('下载内容与已验证模型不一致：'+path.name)
            temporary.replace(path)
            print('Downloaded and verified:', path.name, flush=True)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
