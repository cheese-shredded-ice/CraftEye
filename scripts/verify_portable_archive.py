"""Extract shipped archive to a new path and exercise its actual double-click entrypoints."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--lite',action='store_true')
args=parser.parse_args()
name='CraftEye-v2.1-Lite-Windows-x64' if args.lite else 'CraftEye-v2.1-Windows-x64'
archive=ROOT/'outputs/release'/(name+'.zip')
target=ROOT/'outputs'/('portable-lite-relocation' if args.lite else 'portable-relocation')/'中文目录 with spaces'
target.mkdir(parents=True,exist_ok=True)
package=target/name
assert not package.exists(),'Use a fresh extraction directory.'
with zipfile.ZipFile(archive) as source:
    names=source.namelist()
    assert not any('/logs/' in n or '/outputs/' in n or n.endswith('/secrets.toml') or '/Ultralytics/' in n for n in names)
    assert source.testzip() is None
    for name in names:
        assert (target/name).resolve().is_relative_to(target.resolve())
    source.extractall(target)
digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
assert archive.with_suffix('.zip.sha256').read_text(encoding='utf-8').startswith(digest)
python=package/'runtime/python.exe'
env=os.environ.copy()
env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
for name in list(env):
    if name.startswith('DASHSCOPE_'):
        env.pop(name)
state_file=package/'logs/launcher.json'
command=os.environ.get('COMSPEC','C:/Windows/System32/cmd.exe')
try:
    subprocess.run([command,'/d','/c','启动网页.cmd'],cwd=package,env=env,check=True,timeout=15)
    for _ in range(180):
        try:
            state=json.loads(state_file.read_text(encoding='utf-8'))
            url=f'http://127.0.0.1:{state["port"]}'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url+'/_stcore/health',timeout=1) as response:
                if response.status==200:break
        except (OSError,ValueError):pass
        time.sleep(.5)
    else:raise AssertionError('Extracted launch command failed')
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page()
        page.goto(url,wait_until='domcontentloaded')
        expect(page.get_by_role('button',name='开始识别',exact=True)).to_be_visible(timeout=90000)
        expect(page.get_by_test_id('stException')).to_have_count(0)
        browser.close()
    # Check a direct bundled-model inference after relocation as well.
    result=subprocess.run([str(python),'-I','-B','-X','utf8','-c',
        'from pathlib import Path; from PIL import Image; from inference import infer; from common import DATASET; '
        'image,rows=infer(Image.open(next((DATASET/"test/images").glob("*.jpg"))).convert("RGB"),.25); '
        'assert rows; print("RELOCATED_INFERENCE_OK")'],cwd=package,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=120)
    assert result.returncode==0,result.stdout
    assert 'RELOCATED_INFERENCE_OK' in result.stdout
finally:
    subprocess.run([command,'/d','/c','停止网页.cmd'],cwd=package,env=env,check=True,timeout=15)
    for _ in range(50):
        if not state_file.exists():break
        time.sleep(.5)
    assert not state_file.exists(),'Stop command did not stop the portable app'
verification={'archive_crc':'passed','sha256':digest,'relocation':'Chinese path with spaces',
              'actual_start_cmd':'passed','actual_stop_cmd':'passed','relocated_model_inference':'passed',
              'api_key_included':False,'history_included':False,'files':len(names),'zip_bytes':archive.stat().st_size}
(ROOT/'outputs'/('portable-lite-check' if args.lite else 'portable-check')/'archive-verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps(verification,indent=2))
