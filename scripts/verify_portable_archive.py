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
parser.add_argument('--archive',type=Path)
parser.add_argument('--target',type=Path)
parser.add_argument('--expect-api-key',action='store_true')
args=parser.parse_args()
name='CraftEye-v2.1-Lite-Windows-x64' if args.lite else 'CraftEye-v2.1-Windows-x64'
archive=(args.archive or ROOT/'outputs/release'/(name+'.zip')).resolve()
name=archive.stem
target=(args.target or ROOT/'outputs'/('portable-lite-relocation' if args.lite else 'portable-relocation')/'中文目录 with spaces').resolve()
target.mkdir(parents=True,exist_ok=True)
package=target/name
assert not package.exists(),'Use a fresh extraction directory.'
with zipfile.ZipFile(archive) as source:
    names=source.namelist()
    assert not any('/logs/' in n or '/outputs/' in n or '/Ultralytics/' in n or n.endswith('.sqlite3') for n in names)
    assert any(n.endswith('/secrets.toml') for n in names)==args.expect_api_key
    assert source.testzip() is None
    for name in names:
        assert (target/name).resolve().is_relative_to(target.resolve())
    source.extractall(target)
digest=hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
assert archive.with_suffix('.zip.sha256').read_text(encoding='utf-8').startswith(digest)
python=package/'runtime/python.exe'
env=os.environ.copy()
env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
env['PYTHONPATH']='Z:/no-development-environment'
env['HTTP_PROXY']=env['HTTPS_PROXY']='http://127.0.0.1:1'
env['NO_PROXY']='localhost,127.0.0.1'
for name in list(env):
    if name.startswith('DASHSCOPE_'):
        env.pop(name)
state_file=package/'logs/launcher.json'
command=os.environ.get('COMSPEC','C:/Windows/System32/cmd.exe')
manifest=json.loads((package/'package-manifest.json').read_text(encoding='utf-8'))
assert manifest['api_key_included']==args.expect_api_key
if args.expect_api_key:
    import tomllib
    assert tomllib.loads((package/'.streamlit/secrets.toml').read_text(encoding='utf-8'))['DASHSCOPE_API_KEY']
imports='import onnxruntime,cv2,av,aiortc,streamlit' if manifest['edition']=='lite' else 'import torch,ultralytics,cv2,av,aiortc,streamlit'
audit=subprocess.check_output([str(python),'-I','-B','-X','utf8','-c',
    'import sys,json; '+imports+'; print(json.dumps(dict(paths=sys.path,isolated=sys.flags.isolated)))'],
    cwd=target,env=env,text=True,encoding='utf-8',timeout=90)
audit=json.loads(audit.strip().splitlines()[-1])
assert audit['isolated'] and all(Path(p).resolve().is_relative_to(package) for p in audit['paths']),audit
browser_errors=[]
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
    subprocess.run([command,'/d','/c','启动网页.cmd'],cwd=package,env=env,check=True,timeout=15)
    time.sleep(2)
    assert json.loads(state_file.read_text(encoding='utf-8'))==state,'Duplicate start changed server'
    from playwright.sync_api import sync_playwright, expect
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1366,'height':768},accept_downloads=True)
        page.on('pageerror',lambda error:browser_errors.append(str(error)))
        from urllib.parse import urlsplit
        page.route('**/*',lambda route: route.continue_() if urlsplit(route.request.url).hostname in ('127.0.0.1','localhost') else route.abort())
        page.goto(url,wait_until='domcontentloaded')
        expect(page.get_by_role('button',name='开始识别',exact=True)).to_be_visible(timeout=90000)
        expect(page.get_by_test_id('stException')).to_have_count(0)
        page.screenshot(path=str(target/'startup.png'))
        page.get_by_role('tab',name='识别记录',exact=True).click()
        expect(page.get_by_role('button',name='详情',exact=True).first).to_be_visible(timeout=30000)
        page.get_by_role('button',name='详情',exact=True).first.click()
        expect(page.get_by_role('button',name='下载本次完整记录',exact=True)).to_be_visible(timeout=30000)
        with page.expect_download() as download:
            page.get_by_role('button',name='下载本次完整记录',exact=True).click()
        download.value.save_as(target/'record-detail.zip')
        with zipfile.ZipFile(target/'record-detail.zip') as detail:
            assert detail.testzip() is None
            assert {'report.json','original.png'}.issubset(detail.namelist())
            report=json.loads(detail.read('report.json'))
            assert report['analysis']['dimensions'] and report['complete_snapshot']
        page.get_by_role('button',name='关闭详情',exact=True).click()
        page.get_by_role('tab',name='浏览数据与标注',exact=True).click()
        for label in ('训练集','验证集','测试集'):
            page.get_by_role('combobox',name='数据分组').click()
            page.get_by_role('option',name=label,exact=True).click()
            expect(page.locator('.st-key-browse-image img')).to_be_visible(timeout=30000)
            expect(page.get_by_text('当前分组没有可浏览的图片。',exact=True)).to_have_count(0)
        expect(page.get_by_test_id('stException')).to_have_count(0)
        page.screenshot(path=str(target/'dataset.png'))
        assert not browser_errors,browser_errors
        browser.close()
    # Check a direct bundled-model inference after relocation as well.
    result=subprocess.run([str(python),'-I','-B','-X','utf8','-c',
        'from pathlib import Path; from PIL import Image; from inference import infer; from common import DATASET; '
        'image,rows=infer(Image.open(next((DATASET/"test/images").glob("*.jpg"))).convert("RGB"),.25); '
        'assert rows; image.save("logs/verified-detection.png"); '
        'from recognition_history import load_records; assert len(load_records())==60; '
        'print("RELOCATED_INFERENCE_OK")'],cwd=package,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',timeout=120)
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
              'isolated_imports':'passed','duplicate_start':'passed','dataset_browser':'passed',
              'bundled_records':60,'record_detail_download':'passed','browser_errors':browser_errors,
              'external_http_disabled':True,'real_api_called':False,
              'api_key_included':args.expect_api_key,'history_included':False,'files':len(names)}
(target/'archive-verification.json').write_text(json.dumps(verification,indent=2),encoding='utf-8')
print(json.dumps(verification,indent=2))
