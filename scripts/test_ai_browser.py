"""Browser integration against ai_test_app.py on port 8502 with fake API/camera."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs' / 'ai-check'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/'requests.jsonl').write_text('', encoding='utf-8')
    sample = next((ROOT/'dataset/test/images').glob('bad_weld_vid280*'))
    image = Image.open(sample).convert('RGB')
    image.thumbnail((640, 480))
    canvas = Image.new('RGB', (640, 480), (114,114,114))
    canvas.paste(image, ((640-image.width)//2, (480-image.height)//2))
    yuv = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2YUV_I420).tobytes()
    video = OUTPUT/'fake-camera.y4m'
    with video.open('wb') as output:
        output.write(b'YUV4MPEG2 W640 H480 F10:1 Ip A1:1 C420jpeg\n')
        for _ in range(30):
            output.write(b'FRAME\n'+yuv)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True, args=[
            '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
            '--use-file-for-fake-video-capture='+str(video)])
        context = browser.new_context(permissions=['camera'], accept_downloads=True, viewport={'width':1300,'height':1000})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8502', wait_until='domcontentloaded')
            expect(page.get_by_text('当前端口仅供模拟 AI 接口测试，不会向通义千问发送请求。')).to_be_attached(timeout=60000)
            page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(sample))
            page.get_by_role('button', name='开始识别', exact=True).click(timeout=60000)
            expect(page.get_by_role('button', name='AI 综合分析当前图片', exact=True)).to_be_disabled(timeout=30000)
            page.get_by_text('通义千问 AI 设置', exact=True).click()
            key = page.get_by_label('API Key', exact=True)
            key.fill('test-key-not-real')
            key.press('Tab')
            button = page.get_by_role('button', name='AI 综合分析当前图片', exact=True)
            expect(button).to_be_enabled(timeout=30000)
            button.click()
            expect(page.get_by_text('【图中现象】', exact=True)).to_be_visible(timeout=30000)
            expect(page.get_by_text('【可能原因】', exact=True)).to_be_visible()
            expect(page.get_by_text('【改良建议】', exact=True)).to_be_visible()
            with page.expect_download() as download:
                page.get_by_role('button', name='保存 AI 完整报告（JSON）', exact=True).click()
            download.value.save_as(OUTPUT/'image-ai-report.json')
            report = json.loads((OUTPUT/'image-ai-report.json').read_text(encoding='utf-8'))
            assert report['inputs']['source_type']=='image'
            assert 'test-key-not-real' not in json.dumps(report)
            # Observe several periodic refreshes; none may send another API request.
            page.wait_for_timeout(2500)
            assert len((OUTPUT/'requests.jsonl').read_text().splitlines())==1
            field = page.get_by_label('补充工艺信息（可选）', exact=True)
            field.fill('模拟401')
            field.press('Tab')
            expect(page.get_by_text('图片、补充信息或模型配置已变化，请点击按钮重新分析当前输入。')).to_be_visible(timeout=10000)
            expect(page.get_by_text('【图中现象】', exact=True)).not_to_be_visible()
            button.click()
            expect(page.get_by_text('API Key 验证失败，请检查密钥及所属地域。', exact=True)).to_be_visible(timeout=30000)
            assert 'test-key-not-real must not be displayed' not in page.locator('body').inner_text()
            assert len((OUTPUT/'requests.jsonl').read_text().splitlines())==2
            # Use a fresh browser session to independently verify the camera workflow.
            page.close()
            page = context.new_page()
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto('http://127.0.0.1:8502', wait_until='domcontentloaded')
            expect(page.get_by_text('当前端口仅供模拟 AI 接口测试，不会向通义千问发送请求。')).to_be_attached(timeout=60000)
            page.get_by_text('通义千问 AI 设置', exact=True).click()
            page.get_by_label('API Key', exact=True).fill('test-key-not-real')
            page.get_by_label('API Key', exact=True).press('Tab')
            expect(page.get_by_text('密钥已配置，调用权限将在分析时验证。')).to_be_visible(timeout=30000)
            page.get_by_role('tab',name='摄像头实时识别',exact=True).click()
            iframe = page.frame_locator('iframe[title*="webrtc_streamer"]')
            iframe.get_by_role('button',name='开始实时识别',exact=True).click()
            capture = page.get_by_role('button',name='截取当前结果',exact=True)
            expect(capture).to_be_enabled(timeout=60000)
            capture.click()
            expect(page.get_by_role('button',name='AI 综合分析当前图片',exact=True)).to_be_enabled(timeout=30000)
            page.get_by_role('button',name='AI 综合分析当前图片',exact=True).click()
            expect(page.get_by_text('【图中现象】',exact=True)).to_be_visible(timeout=30000)
            with page.expect_download() as download:
                page.get_by_role('button',name='保存 AI 完整报告（JSON）',exact=True).click()
            download.value.save_as(OUTPUT/'camera-ai-report.json')
            report = json.loads((OUTPUT/'camera-ai-report.json').read_text(encoding='utf-8'))
            assert report['inputs']['source_type']=='camera'
            requests = [json.loads(row) for row in (OUTPUT/'requests.jsonl').read_text().splitlines()]
            assert len(requests)==3 and all(r['distinct_images'] for r in requests)
            page.get_by_text('【图中现象】',exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT/'ai-analysis-simulated.png'),full_page=True)
            iframe.get_by_role('button',name='停止摄像头',exact=True).click()
            expect(capture).to_be_disabled(timeout=30000)
            assert not errors, errors
            print(json.dumps({'image_analysis':'passed','camera_snapshot_analysis':'passed',
                'manual_submit_only':'passed','stale_report_hidden':'passed','safe_401_error':'passed',
                'exports':'passed','simulated_api_requests':len(requests),'real_api_called':False},indent=2),flush=True)
        except Exception:
            page.screenshot(path=str(OUTPUT/'ai-test-failure.png'),full_page=True)
            (OUTPUT/'failure-page.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            print('Browser errors:',errors,flush=True)
            print('Camera controls:', page.frame_locator('iframe[title*="webrtc_streamer"]').locator('body').inner_text(), flush=True)
            raise
        finally:
            context.close()
            browser.close()


if __name__=='__main__':
    main()
