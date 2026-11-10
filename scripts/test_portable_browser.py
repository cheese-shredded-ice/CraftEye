"""Verify a real portable package with no Python/Git on PATH and no API key."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/portable-check'


def main(package):
    global OUT
    lite=json.loads((package/'package-manifest.json').read_text(encoding='utf-8')).get('edition')=='lite'
    if lite:
        OUT=ROOT/'outputs/portable-lite-check'
    OUT.mkdir(exist_ok=True)
    python=package/'runtime/python.exe'
    launcher=package/'launcher.py'
    state_file=package/'logs/launcher.json'
    env=os.environ.copy()
    env['PATH']=os.path.join(os.environ['SystemRoot'],'System32')
    env['PYTHONPATH']='Z:/not-a-python-environment'
    env['GIT_PYTHON_REFRESH']='quiet'
    # Localhost still works; external HTTP(S) cannot fetch dependencies or models.
    env['HTTP_PROXY']=env['HTTPS_PROXY']='http://127.0.0.1:1'
    env['NO_PROXY']='localhost,127.0.0.1'
    for name in list(env):
        if name.startswith('DASHSCOPE_'):
            env.pop(name)
    imports='import onnxruntime,cv2,av,aiortc,streamlit' if lite else 'import torch,torchvision,cv2,av,aiortc,streamlit,ultralytics'
    audit=subprocess.check_output([str(python),'-I','-B','-c',
        'import sys,json; '+imports+'; '
        'print(json.dumps({"paths":sys.path,"isolated":sys.flags.isolated,"no_user_site":sys.flags.no_user_site}))'],
        cwd=OUT,env=env,text=True,timeout=90)
    audit=json.loads(audit.strip().splitlines()[-1])
    assert all(Path(p).resolve().is_relative_to(package) for p in audit['paths']),audit
    assert not (package/'.streamlit/secrets.toml').exists()
    if (package/'outputs/recognition-history.sqlite3').exists():
        import sqlite3
        with sqlite3.connect(package/'outputs/recognition-history.sqlite3') as db:
            assert db.execute('select count(*) from recognition_history').fetchone()[0]==0
    # Reserve 8501 if the development server is not running, to exercise fallback.
    import socket
    occupied=socket.socket()
    try:
        occupied.bind(('127.0.0.1',8501)); occupied.listen()
    except OSError:
        occupied.close(); occupied=None
    process=subprocess.Popen([str(python),'-I','-B',str(launcher),'--no-browser'],
        cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    errors=[]
    try:
        url=None
        for _ in range(180):
            assert process.poll() is None,'Launcher exited before ready.'
            try:
                state=json.loads(state_file.read_text(encoding='utf-8'))
                url=f'http://127.0.0.1:{state["port"]}'
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(url+'/_stcore/health',timeout=1) as response:
                    if response.status==200:break
            except (OSError,ValueError):
                pass
            time.sleep(.5)
        else:
            raise AssertionError('Server did not become healthy.')
        assert state['port']!=8501,state
        subprocess.run([str(python),'-I','-B',str(launcher),'--no-browser'],cwd=OUT,env=env,check=True,timeout=10)
        assert json.loads(state_file.read_text(encoding='utf-8'))==state,'Duplicate launch changed server.'
        sample=next((package/'dataset/test/images').glob('*.jpg'))
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True,args=[
                '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
                '--use-file-for-fake-video-capture='+str(ROOT/'outputs/ai-check/fake-camera.y4m')])
            context=browser.new_context(viewport={'width':1366,'height':768},permissions=['camera'],accept_downloads=True)
            blocked=[]
            def local_only(route):
                from urllib.parse import urlsplit
                if urlsplit(route.request.url).hostname in ('127.0.0.1','localhost'):
                    route.continue_()
                else:
                    blocked.append(route.request.url)
                    route.abort()
            context.route('http://**/*',local_only)
            context.route('https://**/*',local_only)
            page=context.new_page()
            page.on('pageerror',lambda e:errors.append(str(e)))
            try:
                page.goto(url,wait_until='domcontentloaded')
                expect(page.get_by_role('heading',name='数智评鉴系统',exact=True)).to_be_visible(timeout=90000)
                expect(page.get_by_test_id('stException')).to_have_count(0)
                page.get_by_role('tab',name='识别记录',exact=True).click()
                expect(page.get_by_text('暂无记录',exact=False)).to_be_visible(timeout=90000)
                page.get_by_role('tab',name='图片识别',exact=True).click()
                page.get_by_role('button',name='选择图片',exact=True).click()
                page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(sample))
                page.get_by_role('heading',name='数智评鉴系统',exact=True).click()
                page.get_by_role('button',name='开始识别',exact=True).click()
                expect(page.locator('.detection-summary')).to_be_visible(timeout=90000)
                expect(page.get_by_role('button',name='综合分析当前图片',exact=True)).to_be_disabled()
                page.get_by_role('button',name='下载结果',exact=True).click()
                with page.expect_download() as download:
                    page.get_by_role('button',name='保存检测图片',exact=True).click()
                download.value.save_as(OUT/'portable-detection.png')
                page.get_by_role('heading',name='数智评鉴系统',exact=True).click()
                page.screenshot(path=str(OUT/'portable-image.png'))
                page.get_by_role('tab',name='摄像头实时识别',exact=True).click()
                iframe=page.frame_locator('iframe[title*="webrtc_streamer"]')
                iframe.get_by_role('button',name='开始实时识别',exact=True).click()
                capture=page.get_by_role('button',name='截取当前结果',exact=True)
                expect(capture).to_be_enabled(timeout=90000)
                capture.click()
                expect(page.get_by_text('画面已暂停 · 摄像头已关闭',exact=True)).to_be_visible(timeout=30000)
                expect(page.get_by_test_id('stException')).to_have_count(0)
                page.screenshot(path=str(OUT/'portable-camera.png'))
                assert not errors,errors
            except Exception:
                page.screenshot(path=str(OUT/'portable-failure.png'))
                (OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
                raise
            finally:
                context.close(); browser.close()
    finally:
        subprocess.run([str(python),'-I','-B',str(launcher),'--stop','--no-browser'],cwd=OUT,env=env,timeout=15,check=True)
        try:
            process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            process.terminate()
            raise AssertionError('Stop launcher failed.')
        if occupied:
            occupied.close()
    assert process.returncode==0,process.stdout.read()
    assert not state_file.exists()
    result={'portable_imports':audit,'launch':'passed','port_conflict':'passed','duplicate_launch':'passed',
            'stop':'passed','image_detection_and_download':'passed','camera_snapshot':'passed',
            'empty_history':'passed','no_api_key':'passed','browser_errors':errors,'real_api_called':False,
            'external_http_blocked_during_test':True,'external_browser_requests':blocked}
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('package',type=Path)
    main(parser.parse_args().package.resolve())
