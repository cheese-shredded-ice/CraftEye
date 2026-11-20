"""End-to-end test with a synthetic camera; never opens the physical webcam."""
import json
from pathlib import Path
import os
from test_system_browser import configure, close_popover

import cv2
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs' / 'camera-check'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    image = Image.open(next((ROOT/'dataset/test/images').glob('bad_weld_vid280*'))).convert('RGB')
    image.thumbnail((640, 480))
    canvas = Image.new('RGB', (640, 480), (114, 114, 114))
    canvas.paste(image, ((640-image.width)//2, (480-image.height)//2))
    yuv = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2YUV_I420).tobytes()
    video = OUTPUT / 'fake-camera.y4m'
    with video.open('wb') as stream:
        stream.write(b'YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg\n')
        for _ in range(30):
            stream.write(b'FRAME\n' + yuv)
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, args=[
            '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
            '--use-file-for-fake-video-capture=' + str(video),
        ])
        context = browser.new_context(permissions=['camera'], viewport={'width': 1366, 'height': 768}, accept_downloads=True)
        context.add_init_script("""
            window.__cameraTracks = [];
            const original = navigator.mediaDevices?.getUserMedia.bind(navigator.mediaDevices);
            if (original) navigator.mediaDevices.getUserMedia = async (...args) => {
                const stream = await original(...args);
                window.__cameraTracks.push(...stream.getVideoTracks());
                return stream;
            };
        """)
        page = context.new_page()
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(os.environ.get('CRAFTEYE_TEST_URL', 'http://127.0.0.1:8514'), wait_until='domcontentloaded')
        expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
        configure(page)
        page.get_by_role('tab', name='摄像头实时识别', exact=True).click(timeout=60000)
        # Wait for the camera workspace to finish rendering.
        expect(page.locator('.st-key-camera-ai')).to_be_visible(timeout=60000)
        # Keep this end-to-end flow deterministic by explicitly selecting
        # manual capture before testing the capture button and restart flow.
        page.get_by_role('button', name='识别方式', exact=True).click()
        expect(page.get_by_role('radio', name='手动识别', exact=True)).to_be_checked()
        close_popover(page)
        iframe = page.frame_locator('iframe[title*="webrtc_streamer"]')
        try:
            iframe.get_by_role('button', name='开始实时识别', exact=True).click(timeout=60000)
            expect(page.locator('.camera-metrics')).to_be_visible(timeout=60000)
            expect(page.get_by_role('button', name='截取当前结果', exact=True)).to_be_enabled(timeout=30000)
            page.get_by_role('button', name='截取当前结果', exact=True).click()
            expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=30000)
            camera_frame = next(frame for frame in page.frames if 'webrtc_streamer' in frame.url)
            camera_frame.wait_for_function('window.__cameraTracks.length > 0 && window.__cameraTracks.every(track => track.readyState === "ended")')
            expect(page.locator('.st-key-camera-ai .is-complete')).to_be_visible(timeout=60000)
            expect(page.locator('.st-key-camera-stream')).to_be_hidden()
            # Exercise repeated restarts: each capture must release every track,
            # not merely report a stopped peer on the Python side.
            for capture_index in range(3):
                page.get_by_role('button', name='重新拍摄', exact=True).click()
                expect(page.locator('.camera-metrics')).to_be_visible(timeout=60000)
                page.wait_for_function("""() => {
                    const value = document.querySelector('.camera-metrics span:last-child b');
                    return value && Number(value.textContent) >= 12;
                }""")
                expect(page.get_by_role('button', name='截取当前结果', exact=True)).to_be_enabled()
                page.get_by_role('button', name='截取当前结果', exact=True).click()
                expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=30000)
                camera_frame.wait_for_function('window.__cameraTracks.every(track => track.readyState === "ended")')
                expect(page.locator('.st-key-camera-ai .is-complete')).to_be_visible(timeout=30000)
                expect(page.get_by_role('button', name='快照与下载', exact=True)).to_have_count(1)
            for width, height in [(800,450),(1024,600),(1280,720),(1920,1080),(805,1365),(1366,768)]:
                page.set_viewport_size({'width': width, 'height': height})
                bounds = page.get_by_role('button', name='重新拍摄', exact=True).bounding_box()
                stage = page.locator('.st-key-camera-stage').bounding_box()
                assert bounds and stage and bounds['y']+bounds['height'] <= min(height,stage['y']+stage['height'])+1, (width,height,bounds,stage)
            frozen_src = page.locator('.st-key-camera-freeze img').get_attribute('src')
            page.get_by_role('button', name='快照与下载', exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('button', name='保存摄像头报告', exact=True).click()
            download.value.save_as(OUTPUT/'camera-report.json')
            old_url = download.value.url
            close_popover(page)
            report = json.loads((OUTPUT/'camera-report.json').read_text(encoding='utf-8'))
            assert report['source'] == 'camera'
            assert len(report['analysis']['dimensions']) == 6
            assert report['detections'], 'Synthetic welding camera should produce a detection'
            assert 'advice' not in report
            assert 'manual_observations' in report
            assert report['confidence_threshold'] == 0.25
            # A full Streamlit rerun must update threshold without breaking the stream.
            page.get_by_role('button', name='设置', exact=True).click()
            slider = page.get_by_role('slider').first
            slider.focus()
            slider.press('ArrowRight')
            close_popover(page)
            expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=30000)
            assert page.locator('.st-key-camera-freeze img').get_attribute('src') == frozen_src
            page.get_by_role('button', name='重新拍摄', exact=True).click()
            expect(page.locator('[data-live-threshold="0.30"]')).to_be_visible(timeout=60000)
            expect(page.get_by_role('button', name='截取当前结果', exact=True)).to_be_enabled(timeout=30000)
            page.get_by_role('button', name='截取当前结果', exact=True).click()
            expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=30000)
            camera_frame.wait_for_function('window.__cameraTracks.length > 0 && window.__cameraTracks.every(track => track.readyState === "ended")')
            expect(page.locator('.st-key-camera-ai .is-complete')).to_be_visible(timeout=30000)
            page.get_by_role('button', name='快照与下载', exact=True).click()
            expect(page.get_by_text('快照阈值：30%', exact=False)).to_be_visible(timeout=15000)
            with page.expect_download() as changed_download:
                page.get_by_role('button', name='保存摄像头报告', exact=True).click()
            changed_download.value.save_as(OUTPUT/'camera-report-threshold.json')
            assert changed_download.value.url != old_url
            changed = json.loads((OUTPUT/'camera-report-threshold.json').read_text(encoding='utf-8'))
            assert changed['confidence_threshold'] == 0.30
            close_popover(page)
            page.get_by_role('tab', name='摄像头实时识别', exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT/'camera-running.png'), full_page=True)
            page.get_by_role('button', name='快照与下载', exact=True).click()
            page.get_by_role('button', name='清除快照', exact=True).click()
            expect(page.get_by_text('摄像头未运行。', exact=False)).to_be_visible(timeout=30000)
            expect(page.get_by_role('button', name='截取当前结果', exact=True)).to_be_disabled()
            iframe.get_by_role('button', name='开始实时识别', exact=True).click()
            expect(page.get_by_role('button', name='截取当前结果', exact=True)).to_be_enabled(timeout=60000)
            iframe.get_by_role('button', name='停止摄像头', exact=True).click()
            expect(page.get_by_text('摄像头未运行。', exact=False)).to_be_visible(timeout=30000)
            page.get_by_role('button', name='识别方式', exact=True).click()
            page.get_by_text('自动识别', exact=True).click()
            close_popover(page)
            iframe.get_by_role('button', name='开始实时识别', exact=True).click()
            expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=60000)
            expect(page.locator('.st-key-camera-ai .is-complete')).to_be_visible(timeout=30000)
            camera_frame.wait_for_function('window.__cameraTracks.every(track => track.readyState === "ended")')
            result = {'synthetic_camera': True, 'start_stop_restart': 'passed',
                'detections': report['detections'], 'report_export': 'passed',
                'live_threshold_update': 'passed', 'capture_stops_media_tracks': 'passed', 'repeated_restarts': 'passed', 'manual_survives_twelve_frames': 'passed', 'frozen_image_stable': 'passed', 'automatic_capture': 'passed', 'six_frozen_viewports': 'passed', 'browser_errors': errors}
            (OUTPUT/'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            assert not errors, errors
        except Exception:
            page.screenshot(path=str(OUTPUT/'camera-failure.png'), full_page=True)
            (OUTPUT/'failure-page.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
            print('Frame URLs:', [f.url for f in page.frames], flush=True)
            print('Camera check failed; see failure-page.txt', flush=True)
            print('Browser errors:', errors, flush=True)
            for frame in page.frames:
                if 'webrtc_streamer' in frame.url:
                    print('Track states:', frame.evaluate('window.__cameraTracks?.map(t=>({id:t.id,state:t.readyState,label:t.label}))'), flush=True)
            raise
        finally:
            context.close()
            browser.close()


if __name__ == '__main__':
    main()
