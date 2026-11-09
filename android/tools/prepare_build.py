"""Download official Android build tools and the author's verified ONNX export."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('D:/welding-android-tools')


def download(url, target, checksum=None, algorithm='sha1'):
    target.parent.mkdir(parents=True, exist_ok=True)
    def valid(path):
        return path.exists() and (not checksum or hashlib.new(algorithm, path.read_bytes()).hexdigest() == checksum)
    if valid(target):
        return target
    import time
    for attempt in range(5):
        try:
            temp = target.with_suffix(target.suffix + '.part')
            with urllib.request.urlopen(url, timeout=90) as response, temp.open('wb') as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
            if not valid(temp):
                raise ValueError(f'Checksum mismatch: {target.name}')
            temp.replace(target)
            print(f'Downloaded {target.name}', flush=True)
            return target
        except Exception:
            if attempt == 4:
                raise
            time.sleep(2 ** attempt)


def main():
    TOOLS.mkdir(parents=True, exist_ok=True)
    repo = ET.parse(ROOT / 'tools/repository.xml').getroot()
    # SDK components are installed for this requested local Android build.
    for license in repo.findall('license'):
        if license.attrib['id'] == 'android-sdk-license':
            license_text = license.text or ''
            license_dir = TOOLS / 'sdk/licenses'
            license_dir.mkdir(parents=True, exist_ok=True)
            hashes = {hashlib.sha1(value.encode()).hexdigest() for value in (license_text, license_text.strip())}
            (license_dir / 'android-sdk-license').write_text('\n'.join(sorted(hashes)) + '\n', encoding='ascii')
            (ROOT / 'tools/android-sdk-license.txt').write_text(license_text, encoding='utf-8')
    packages = {'platforms;android-35': 'platforms/android-35',
                'build-tools;35.0.0': 'build-tools/35.0.0', 'platform-tools': 'platform-tools'}
    jobs = []
    seen = set()
    for package in repo.findall('remotePackage'):
        name = package.attrib['path']
        if name not in packages or name in seen:
            continue
        seen.add(name)
        for archive in package.findall('./archives/archive'):
            if archive.findtext('host-os') not in (None, 'windows'):
                continue
            complete = archive.find('complete')
            jobs.append((complete.findtext('url'), complete.findtext('checksum'), packages[name]))

    def sdk_package(job):
        filename, checksum, relative = job
        dest = TOOLS / 'sdk' / relative
        if (dest / 'source.properties').exists():
            return
        archive = download('https://dl.google.com/android/repository/' + filename, TOOLS / 'downloads' / filename, checksum)
        extract = TOOLS / 'unpack' / filename.removesuffix('.zip')
        with zipfile.ZipFile(archive) as z:
            z.extractall(extract)
        properties = next(extract.rglob('source.properties'))
        shutil.copytree(properties.parent, dest, dirs_exist_ok=True)
        print(f'Installed {relative}', flush=True)

    def gradle():
        url = 'https://downloads.gradle.org/distributions/gradle-8.9-bin.zip'
        checksum = urllib.request.urlopen(url + '.sha256', timeout=30).read().decode().strip()
        archive = download(url, TOOLS / 'downloads/gradle-8.9-bin.zip', checksum, 'sha256')
        if not (TOOLS / 'gradle-8.9/bin/gradle.bat').exists():
            with zipfile.ZipFile(archive) as z:
                z.extractall(TOOLS)
        print('Gradle ready', flush=True)

    def model():
        dest = ROOT / 'app/src/main/assets/welding.onnx'
        checksum = 'dbddf8b39a4425b53aad2de279e0fb18b2189f97afdf9ad1c5a939cf59b29745'
        download('https://huggingface.co/avinashhm/welding-defect-yolov8-full-training/resolve/2cbc6dc08b74b6bab1ebafc59a3804e4bc43e517/weights/best.onnx', dest, checksum, 'sha256')
        print('Author ONNX model verified', flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(sdk_package, job) for job in jobs] + [pool.submit(gradle), pool.submit(model)]
        for future in concurrent.futures.as_completed(futures):
            future.result()
    (ROOT / 'local.properties').write_text('sdk.dir=D:/welding-android-tools/sdk\n', encoding='utf-8')
    print('All build dependencies ready.', flush=True)


if __name__ == '__main__':
    main()
