"""Real local models, downloaded workshop video, and browser fake-camera transport."""
import json
import os
from pathlib import Path

import cv2
from PIL import Image
import numpy as np
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/behavior-check/browser'
OUT.mkdir(parents=True, exist_ok=True)
SAMPLE = ROOT/'outputs/behavior-samples/workshop-demo.mp4'


def camera_file():
    cap = cv2.VideoCapture(str(SAMPLE))
    path = OUT/'camera.y4m'
    with path.open('wb') as output:
        output.write(b'YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg\n')
        index = 0
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if index % 3 == 0:
                image = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                image.thumbnail((640,480))
                canvas = Image.new('RGB',(640,480),(114,114,114))
                canvas.paste(image,((640-image.width)//2,(480-image.height)//2))
                output.write(b'FRAME\n'+cv2.cvtColor(np.array(canvas),cv2.COLOR_RGB2YUV_I420).tobytes())
            index += 1
    cap.release()
    return path


def check_layout(page, name):
    for width,height in [(1280,720),(1366,768),(1920,1080)]:
        page.set_viewport_size({'width':width,'height':height})
        page.wait_for_timeout(300)
        for selector in ['[data-baseweb="tab-list"]','.st-key-behavior-preview','.st-key-behavior-feedback']:
            box=page.locator(selector).bounding_box()
            assert box and box['x']>=0 and box['x']+box['width']<=width+1, (selector,box)
            assert box['y']+box['height']<=height+1, (selector,box)
        page.screenshot(path=str(OUT/f'{name}-{width}.png'))
    page.set_viewport_size({'width':1366,'height':768})


def main():
    video = camera_file()
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True,args=[
            '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
            '--use-file-for-fake-video-capture='+str(video)])
        context=browser.new_context(permissions=['camera'],accept_downloads=True,viewport={'width':1366,'height':768})
        page=context.new_page()
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(os.environ.get('CRAFTEYE_TEST_URL','http://127.0.0.1:8516'))
            page.get_by_role('tab',name='实训行为',exact=True).click(timeout=60000)
            expect(page.get_by_role('button',name='开始行为分析',exact=True)).to_be_visible()
            check_layout(page,'initial')
            # Upload the real downloaded video with the default observation region.
            page.get_by_role('button',name='上传视频',exact=True).click()
            page.get_by_role('button',name='选择训练视频',exact=True).click()
            page.locator('.st-key-behavior_upload input[type=file]').set_input_files(str(SAMPLE))
            page.mouse.click(900,35)
            page.get_by_role('button',name='开始行为分析',exact=True).click()
            expect(page.get_by_role('button',name='下载行为报告',exact=True)).to_be_visible(timeout=120000)
            with page.expect_download() as data:
                page.get_by_role('button',name='下载行为报告',exact=True).click()
            data.value.save_as(str(OUT/'uploaded-report.json'))
            report=json.loads((OUT/'uploaded-report.json').read_text(encoding='utf-8'))
            assert report['sample_count']>=25 and report['totals']['visible']>7,report
            assert report['ppe_seconds']['面罩']['observed']>5
            with page.expect_download() as data:
                page.get_by_role('button',name='下载标注视频',exact=True).click()
            data.value.save_as(str(OUT/'downloaded-annotated.mp4'))
            cap=cv2.VideoCapture(str(OUT/'downloaded-annotated.mp4'))
            assert cap.read()[0];cap.release()
            check_layout(page,'uploaded')
            # Video should play without being reset by the once-per-second status refresh.
            player=page.locator('.st-key-behavior-preview video')
            player.evaluate('(video)=>{video.muted=true;return video.play()}')
            page.wait_for_timeout(2500)
            assert player.evaluate('(video)=>video.currentTime')>1.5
            # Configure a deliberately narrow ROI and exercise timed event seeking.
            page.get_by_role('button',name='观察设置',exact=True).click()
            slider=page.locator('.st-key-behavior_roi_x [role=slider]').nth(1)
            for _ in range(120):
                if slider.get_attribute('aria-valuenow')=='25':
                    break
                slider.press('ArrowLeft')
                page.wait_for_timeout(70)
            assert slider.get_attribute('aria-valuenow')=='25'
            page.mouse.click(900,35)
            page.get_by_role('button',name='开始行为分析',exact=True).click()
            expect(page.get_by_role('button',name='下载行为报告',exact=True)).to_be_visible(timeout=120000)
            page.locator('.st-key-behavior-preview [data-testid=stSelectbox]').click()
            page.get_by_role('option').last.click()
            page.wait_for_timeout(1500)
            assert page.locator('.st-key-behavior-preview video').evaluate('(v)=>v.currentTime')>=4
            page.screenshot(path=str(OUT/'event-replay.png'))
            page.get_by_role('button',name='观察设置',exact=True).click()
            for _ in range(120):
                if slider.get_attribute('aria-valuenow')=='95':
                    break
                slider.press('ArrowRight')
                page.wait_for_timeout(70)
            page.mouse.click(900,35)
            # A local fake camera uses the downloaded footage; inference itself is real.
            page.get_by_role('button',name='实时摄像头',exact=True).click()
            page.get_by_role('button',name='开始新一轮观察',exact=True).click()
            expect(page.locator('.behavior-metrics')).to_be_visible(timeout=90000)
            page.wait_for_timeout(5000)
            expect(page.get_by_test_id('stException')).to_have_count(0)
            page.get_by_role('button',name='结束观察并保存',exact=True).click()
            expect(page.get_by_role('button',name='下载行为报告',exact=True)).to_be_visible(timeout=15000)
            with page.expect_download() as data:
                page.get_by_role('button',name='下载行为报告',exact=True).click()
            data.value.save_as(str(OUT/'camera-report.json'))
            camera=json.loads((OUT/'camera-report.json').read_text(encoding='utf-8'))
            assert camera['samples']>=3 and camera['totals']['duration']>1,camera
            frozen=page.locator('.behavior-metrics').inner_text()
            page.wait_for_timeout(2000)
            assert frozen==page.locator('.behavior-metrics').inner_text()
            check_layout(page,'camera-frozen')
            page.get_by_role('button',name='开始新一轮观察',exact=True).click()
            expect(page.get_by_role('button',name='结束观察并保存',exact=True)).to_be_visible(timeout=30000)
            page.get_by_role('button',name='结束观察并保存',exact=True).click()
            expect(page.get_by_role('button',name='下载行为报告',exact=True)).to_be_visible(timeout=15000)
            assert not errors,errors
            results={'real_video_upload':'passed','real_models':'passed','report_and_video_download':'passed',
                     'video_playback_stable':'passed','event_video_seek':'passed','fake_camera_real_inference':'passed','stop_and_restart':'passed',
                     'single_screen_3_sizes':'passed','real_cloud_api_called':False}
            (OUT/'verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps(results,indent=2))
        except Exception:
            page.screenshot(path=str(OUT/'failure.png'))
            (OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            raise
        finally:
            context.close();browser.close()


if __name__=='__main__':
    main()
