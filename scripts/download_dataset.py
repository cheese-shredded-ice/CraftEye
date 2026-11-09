"""Download the complete, pinned Hugging Face dataset; verify every file."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'dataset'
REPO = 'avinashhm/the-welding-defect-dataset-v2'
REVISION = '330f89743529aafa8f281c9af88cd648f359a890'


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'welding-local-setup/1.0'}), timeout=60)


def matches(path, entry):
    if not path.is_file() or path.stat().st_size != entry['size']:
        return False
    data = path.read_bytes()
    if entry.get('lfs'):
        return hashlib.sha256(data).hexdigest() == entry['lfs']['oid']
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['oid']


def download(entry):
    target = DEST / entry['path']
    if matches(target, entry):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f'https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/' + urllib.parse.quote(entry['path'])
    temp = target.with_name(target.name + '.part')
    for attempt in range(6):
        try:
            with request(url) as response, temp.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if not matches(temp, entry):
                raise ValueError(f'Checksum mismatch: {entry["path"]}')
            os.replace(temp, target)
            return
        except Exception:
            if attempt == 5:
                raise
            time.sleep(min(2 ** attempt, 20))


def prefetch(entries):
    """Fetch small Git blobs together and images in three Parquet files."""
    import pyarrow.parquet as pq
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)
    git_dir = cache / 'dataset.git'
    env = os.environ.copy()
    env.update({key.upper() + '_PROXY': value for key, value in urllib.request.getproxies().items()
                if key in ('http', 'https')})
    if not git_dir.exists():
        subprocess.run(['git', 'clone', '--bare', '--depth', '1',
                        f'https://huggingface.co/datasets/{REPO}', str(git_dir)], env=env, check=True)
    revision = subprocess.check_output(['git', '--git-dir', str(git_dir), 'rev-parse', 'HEAD']).decode().strip()
    if revision != REVISION:
        subprocess.run(['git', '--git-dir', str(git_dir), 'fetch', '--depth', '1', 'origin', REVISION], env=env, check=True)
    small = [e for e in entries if not e.get('lfs') and not matches(DEST / e['path'], e)]
    if small:
        result = subprocess.run(['git', '--git-dir', str(git_dir), 'cat-file', '--batch'],
                                input=''.join(e['oid'] + '\n' for e in small).encode(),
                                stdout=subprocess.PIPE, check=True).stdout
        offset = 0
        for entry in small:
            end = result.index(b'\n', offset)
            size = int(result[offset:end].split()[2])
            data = result[end + 1:end + 1 + size]
            offset = end + 2 + size
            target = DEST / entry['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if not matches(target, entry):
                raise ValueError(f'Git blob verification failed: {entry["path"]}')
    print('All text annotations downloaded and verified.', flush=True)

    def extract(split):
        local_split = 'valid' if split == 'validation' else split
        wanted = {Path(e['path']).name: e for e in entries if e['path'].startswith(local_split + '/images/')}
        if all(matches(DEST / e['path'], e) for e in wanted.values()):
            return
        parquet = cache / (split + '.parquet')
        if not parquet.exists():
            url = f'https://huggingface.co/datasets/{REPO}/resolve/refs%2Fconvert%2Fparquet/default/{split}/0000.parquet'
            temp = parquet.with_suffix('.part')
            for attempt in range(5):
                try:
                    with request(url) as response, temp.open('wb') as out:
                        while chunk := response.read(1024 * 1024):
                            out.write(chunk)
                    pq.read_metadata(temp)
                    temp.replace(parquet)
                    break
                except Exception:
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
        for batch in pq.ParquetFile(parquet).iter_batches(batch_size=32):
            for row in batch.to_pylist():
                image = row['image']
                entry = wanted.get(Path(image['path']).name)
                if entry is None:
                    continue
                target = DEST / entry['path']
                if matches(target, entry):
                    continue
                data = image['bytes']
                if hashlib.sha256(data).hexdigest() != entry['lfs']['oid']:
                    continue  # Fall back to the exact pinned original below.
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        print(f'{local_split}: image archive extracted and verified.', flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(extract, ['test', 'train', 'validation']))


def main():
    DEST.mkdir(exist_ok=True)
    receipt = ROOT / 'dataset-manifest.json'
    if receipt.exists():
        entries = json.loads(receipt.read_text(encoding='utf-8'))['files']
    else:
        entries = []
        url = f'https://huggingface.co/api/datasets/{REPO}/tree/{REVISION}?recursive=true&limit=1000'
        while url:
            with request(url) as response:
                entries.extend(e for e in json.load(response) if e['type'] == 'file')
                link = response.headers.get('Link', '')
                url = next((part.split('>')[0].strip().lstrip('<') for part in link.split(',') if 'rel="next"' in part), None)
        receipt.write_text(json.dumps({'repo': REPO, 'revision': REVISION, 'files': entries}, indent=2), encoding='utf-8')
    print(f'Downloading/verifying {len(entries)} files, {sum(e["size"] for e in entries):,} bytes', flush=True)
    try:
        prefetch(entries)
    except Exception as exc:
        print(f'Archive prefetch unavailable; continuing individual downloads: {exc}', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(download, entry): entry for entry in entries}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            if i % 100 == 0 or i == len(entries):
                print(f'Verified {i}/{len(entries)}', flush=True)
    print('Download complete. All file checksums match the source revision.', flush=True)


if __name__ == '__main__':
    main()
