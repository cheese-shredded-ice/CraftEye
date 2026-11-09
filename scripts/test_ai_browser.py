"""Browser integration against ai_test_app.py on port 8502 with fake API/camera."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs' / 'ai-check'


def assert_single_screen(page, *panels):
    result = page.evaluate('''(panels) => {
        const failures = [];
        for (const selector of ['html', 'body', '[data-testid="stMain"]', ...panels]) {
            const element = document.querySelector(selector);
            if (!element) { failures.push(selector + ': missing'); continue; }
            const box = element.getBoundingClientRect();
            if (box.left < -1 || box.right > innerWidth + 1 || box.bottom > innerHeight + 1)
                failures.push(selector + ': outside viewport ' + JSON.stringify(box.toJSON()));
            if (element.scrollHeight > element.clientHeight + 2 || element.scrollWidth > element.clientWidth + 2)
                failures.push(selector + ': overflowing ' + element.scrollHeight + '/' + element.clientHeight);
        }
        const report = document.querySelector(panels[1] + ' .teaching-report');
        if (report && report.scrollHeight > report.clientHeight + 2) failures.push('report text clipped');
        if (report && parseFloat(getComputedStyle(report).fontSize) < 18) failures.push('presentation text too small');
        if (report && [...report.querySelectorAll('.feedback-text p')].some(el => parseFloat(getComputedStyle(el).fontSize) < 18)) failures.push('feedback text too small');
        for (const image of document.querySelectorAll(panels[1] + ' .reference-grid img'))
            if (!image.complete || !image.naturalWidth) failures.push('reference image not loaded');
        return failures;
    }''', list(panels))
    assert not result, result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT/'history-test.sqlite3').unlink(missing_ok=True)
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
        context = browser.new_context(permissions=['camera'], accept_downloads=True, viewport={'width':1366,'height':768})
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8502', wait_until='domcontentloaded')
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('tab', name='识别记录', exact=True).click()
            expect(page.get_by_text('暂无记录', exact=False)).to_be_visible()
            page.get_by_role('tab', name='图片识别', exact=True).click()
            page.get_by_role('button', name='选择图片', exact=True).click()
            page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(sample))
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            page.get_by_role('button', name='开始识别', exact=True).click(timeout=60000)
            expect(page.locator('button:visible').filter(has_text='综合分析当前图片').last).to_be_disabled(timeout=30000)
            page.get_by_role('button', name='设置', exact=True).click()
            page.get_by_text('分析设置', exact=True).click()
            key = page.get_by_label('API Key', exact=True)
            key.fill('test-key-not-real')
            key.press('Tab')
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            button = page.locator('button:visible').filter(has_text='综合分析当前图片').last
            expect(button).to_be_enabled(timeout=30000)
            button.click()
            expect(page.get_by_text('【图中现象】', exact=True)).to_be_visible(timeout=30000)
            expect(page.get_by_text('【缺陷类型】', exact=True)).to_be_visible()
            expect(page.locator('[data-weld-score="76"]')).to_be_visible()
            expect(page.locator('[aria-label="缺陷对比图"]')).to_be_visible()
            expect(page.get_by_text('气孔 · 典型示例', exact=True)).to_be_visible()
            expect(page.get_by_text('咬边 · 典型示例', exact=True)).to_be_visible()
            expect(page.locator('[data-score-ring="76"]')).to_be_visible()
            assert '180, 83, 9' in page.locator('[data-score-ring]').evaluate('(el) => getComputedStyle(el).backgroundImage')
            for removed in ('0–59 红色', '本地运行 · 图片检测', '三类标签：', '未检出目标不代表焊接合格'):
                assert removed not in page.locator('body').inner_text()
            page.screenshot(path=str(OUTPUT/'image-score-references.png'),full_page=True)
            expect(page.get_by_text('【可能原因】', exact=True)).to_be_visible()
            expect(page.get_by_text('【改良建议】', exact=True)).to_be_visible()
            for width, height in ((1366, 768), (1280, 720), (1920, 1080)):
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_timeout(200)
                assert_single_screen(page, '.st-key-image-stage', '.st-key-image-ai')
                page.screenshot(path=str(OUTPUT/f'workspace-{width}x{height}.png'))
            page.set_viewport_size({'width':1366,'height':768})
            page.get_by_role('button', name='下载分析报告', exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('button', name='保存完整分析报告（JSON）', exact=True).click()
            download.value.save_as(OUTPUT/'image-ai-report.json')
            report = json.loads((OUTPUT/'image-ai-report.json').read_text(encoding='utf-8'))
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            assert report['inputs']['source_type']=='image'
            assert report['analysis']['sections']['缺陷类型']
            assert report['analysis']['score']['分数'] == 76
            assert report['analysis']['focus_regions']
            assert all(region['confidence'] > 0.6 for region in report['analysis']['focus_regions'])
            assert 'test-key-not-real' not in json.dumps(report)
            # Observe several periodic refreshes; none may send another API request.
            page.wait_for_timeout(2500)
            assert len((OUTPUT/'requests.jsonl').read_text().splitlines())==1
            page.get_by_role('button', name='设置', exact=True).click()
            field = page.get_by_label('视觉模型', exact=True)
            field.fill('simulate-401')
            field.press('Tab')
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            expect(page.get_by_text('图片、现场现象或模型配置已变化，请点击按钮重新分析当前输入。')).to_be_visible(timeout=10000)
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
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('button', name='设置', exact=True).click()
            page.get_by_text('分析设置', exact=True).click()
            page.get_by_label('API Key', exact=True).fill('test-key-not-real')
            page.get_by_label('API Key', exact=True).press('Tab')
            expect(page.get_by_text('密钥已配置，调用权限将在分析时验证。')).to_be_visible(timeout=30000)
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            page.get_by_role('tab',name='摄像头实时识别',exact=True).click()
            iframe = page.frame_locator('iframe[title*="webrtc_streamer"]')
            iframe.get_by_role('button',name='开始实时识别',exact=True).click()
            capture = page.get_by_role('button',name='截取当前结果',exact=True)
            expect(capture).to_be_enabled(timeout=60000)
            capture.click()
            expect(page.get_by_text('画面已暂停 · 摄像头已关闭', exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('button:visible').filter(has_text='综合分析当前图片').last).to_be_enabled(timeout=30000)
            page.locator('button:visible').filter(has_text='综合分析当前图片').last.click()
            expect(page.get_by_text('【图中现象】',exact=True)).to_be_visible(timeout=30000)
            expect(page.locator('[data-weld-score="76"]')).to_be_visible()
            expect(page.get_by_text('气孔 · 典型示例', exact=True)).to_be_visible()
            for width, height in ((1366, 768), (1280, 720), (1920, 1080)):
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_timeout(200)
                assert_single_screen(page, '.st-key-camera-stage', '.st-key-camera-ai')
                page.screenshot(path=str(OUTPUT/f'camera-workspace-{width}x{height}.png'))
            page.set_viewport_size({'width':1366,'height':768})
            page.get_by_role('button', name='下载分析报告', exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('button',name='保存完整分析报告（JSON）',exact=True).click()
            download.value.save_as(OUTPUT/'camera-ai-report.json')
            page.get_by_role('heading', name='匠眼·慧焊 数智评鉴系统', exact=True).click()
            report = json.loads((OUTPUT/'camera-ai-report.json').read_text(encoding='utf-8'))
            assert report['inputs']['source_type']=='camera'
            assert report['analysis']['score']['分数'] == 76
            assert report['analysis']['sections']['缺陷类型']
            requests = [json.loads(row) for row in (OUTPUT/'requests.jsonl').read_text().splitlines()]
            assert len(requests)==3 and all(r['distinct_images'] for r in requests)
            assert all(r['focus_crops'] > 0 for r in requests)
            page.get_by_text('【图中现象】',exact=True).scroll_into_view_if_needed()
            page.screenshot(path=str(OUTPUT/'ai-analysis-simulated.png'),full_page=True)
            page.get_by_role('button',name='快照与下载',exact=True).click()
            page.get_by_role('button',name='清除快照',exact=True).click()
            expect(capture).to_be_disabled(timeout=30000)
            page.get_by_role('tab', name='识别记录', exact=True).click()
            expect(page.locator('.history-table tbody tr')).to_have_count(2, timeout=10000)
            expect(page.get_by_text('分数成长曲线', exact=True)).to_be_visible()
            page.wait_for_timeout(2500)
            expect(page.locator('.history-table tbody tr')).to_have_count(2)
            page.reload()
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('tab', name='识别记录', exact=True).click()
            expect(page.locator('.history-table tbody tr')).to_have_count(2, timeout=10000)
            assert not errors, errors
            print(json.dumps({'image_analysis':'passed','camera_snapshot_analysis':'passed',
                'single_screen_desktop_sizes':'passed',
                'history_persistence_and_deduplication':'passed',
                'manual_submit_only':'passed','stale_report_hidden':'passed','safe_401_error':'passed',
                'exports':'passed','simulated_api_requests':len(requests),'real_api_called':False},indent=2),flush=True)
        except Exception:
            page.screenshot(path=str(OUTPUT/'ai-test-failure.png'),full_page=True)
            (OUTPUT/'failure-page.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            print('Browser errors:',errors,flush=True)
            if page.locator('iframe[title*="webrtc_streamer"]').count():
                print('Camera controls:', page.frame_locator('iframe[title*="webrtc_streamer"]').locator('body').inner_text(timeout=3000), flush=True)
            raise
        finally:
            context.close()
            browser.close()


if __name__=='__main__':
    main()
