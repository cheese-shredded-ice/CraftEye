"""Current UI regression using ai_test_app.py; no real API or user history writes."""
import json
import os
from pathlib import Path
import sys
from PIL import Image

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'outputs/system-check'
URL = os.environ.get('CRAFTEYE_TEST_URL', 'http://127.0.0.1:8514')
SAMPLE = ROOT / 'assets/weld-examples/uniform.jpg'


def close_popover(page):
    page.keyboard.press('Escape')  # Close an open select menu inside the popover.
    page.mouse.click(5, 5)
    expect(page.locator('[data-testid="stPopoverBody"]')).to_have_count(0)


def configure(page, model='test-model', key='test-key-not-real'):
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_label('API Key', exact=True).fill(key)
    page.get_by_label('API Key', exact=True).press('Tab')
    page.get_by_label('视觉模型', exact=True).fill(model)
    page.get_by_label('视觉模型', exact=True).press('Tab')
    expect(page.get_by_label('视觉模型', exact=True)).to_have_value(model)
    page.wait_for_timeout(400)
    close_popover(page)


def upload(page, path=SAMPLE):
    page.get_by_role('button', name='选择图片', exact=True).click()
    page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(path))
    expect(page.get_by_role('button', name='开始识别', exact=True)).to_be_enabled(timeout=30000)
    close_popover(page)
    expect(page.get_by_role('button', name='开始识别', exact=True)).to_be_enabled()


def start(page):
    page.get_by_role('button', name='开始识别', exact=True).click()


def stable_panel(page):
    expect(page.locator('.st-key-image-ai .teaching-report')).to_have_count(1)
    expect(page.locator('.st-key-image-ai .analysis-status-only')).to_have_count(1)
    expect(page.get_by_test_id('stException')).to_have_count(0)


def no_key_keeps_layout(page):
    upload(page)
    start(page)
    expect(page.locator('.st-key-image-stage .detection-summary')).to_be_visible(timeout=60000)
    stable_panel(page)
    expect(page.locator('.st-key-image-ai .score-status')).to_have_text('-')
    stage = page.locator('.st-key-image-stage')
    annotated_src = stage.locator('[data-testid="stImage"] img').get_attribute('src')
    stage.get_by_text('原图', exact=True).click()
    expect(stage.locator('[data-testid="stImage"] img')).not_to_have_attribute('src', annotated_src)
    stage.get_by_text('检测结果', exact=True).click()
    expect(stage.locator('[data-testid="stImage"] img')).to_have_attribute('src', annotated_src)
    stage.get_by_role('button', name='现场现象', exact=True).click()
    page.get_by_role('combobox', name='补充现场现象（可选，人工选择）').click()
    page.get_by_role('option', name='烧穿、熔池过大或边缘塌陷', exact=True).click()
    page.keyboard.press('Escape')
    stage.get_by_role('button', name='现场现象', exact=True).click()
    expect(page.locator('[data-testid="stPopoverBody"]')).to_have_count(0)
    page.get_by_role('button', name='下载结果', exact=True).click()
    for label in ('保存检测图片','保存检测数据','保存完整报告'):
        with page.expect_download() as download:
            page.get_by_role('button', name=label, exact=True).click()
        path = download.value.path()
        if label == '保存检测图片':
            with Image.open(path) as img, Image.open(SAMPLE) as original:
                assert img.size == original.size
                img.verify()
        else:
            content = json.loads(path.read_text(encoding='utf-8'))
            if label == '保存完整报告':
                assert content['manual_observations'] == ['烧穿、熔池过大或边缘塌陷']
                assert 'analysis' not in content
            else:
                assert isinstance(content,list)


def clear_during_analysis_recovers(page):
    configure(page, 'simulate-slow')
    upload(page)
    start(page)
    expect(page.locator('.st-key-image-ai .is-analyzing')).to_be_visible(timeout=60000)
    page.get_by_role('button', name='选择图片', exact=True).click()
    page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files([])
    close_popover(page)
    page.wait_for_timeout(8500)
    upload(page, ROOT / 'assets/weld-examples/crack.jpg')
    start(page)
    expect(page.locator('.st-key-image-ai .is-complete')).to_be_visible(timeout=30000)
    stable_panel(page)


def error_and_retry(page):
    configure(page, 'simulate-401')
    upload(page)
    start(page)
    expect(page.get_by_text('API Key 验证失败，请检查密钥及所属地域。', exact=True)).to_be_visible(timeout=60000)
    stable_panel(page)
    assert 'test-key-not-real must not be displayed' not in page.locator('body').inner_text()
    configure(page)
    page.locator('.st-key-image-ai').get_by_role('button', name='综合分析当前图片', exact=True).click()
    expect(page.locator('.st-key-image-ai .is-complete')).to_be_visible(timeout=30000)
    stable_panel(page)
    page.locator('.st-key-image-ai').get_by_text('改进建议', exact=True).click()
    expect(page.locator('.st-key-image-ai .feedback-row')).to_have_count(4)
    expect(page.locator('.st-key-image-ai .reference-grid figure').first).to_be_visible()
    page.get_by_role('button', name='下载结果', exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button', name='保存完整报告', exact=True).click()
    saved = json.loads(download.value.path().read_text(encoding='utf-8'))
    assert len(saved['analysis']['dimensions']) == 6 and saved['analysis']['score']['最终分'] == 73
    assert 'test-key-not-real' not in json.dumps(saved)
    close_popover(page)
    configure(page, 'simulate-crack')
    page.get_by_role('button', name='下载结果', exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button', name='保存完整报告', exact=True).click()
    assert 'analysis' not in json.loads(download.value.path().read_text(encoding='utf-8'))


def engineering_evidence(page):
    page.get_by_role('button', name='设置', exact=True).click()
    page.get_by_role('button', name='技术与验证', exact=True).click()
    dialog = page.get_by_role('dialog')
    expect(dialog.get_by_text('项目定制的核心实现')).to_be_visible()
    with page.expect_download() as download:
        dialog.get_by_role('button', name='下载技术证据清单', exact=True).click()
    manifest = json.loads(download.value.path().read_text(encoding='utf-8'))
    assert manifest['product'] == 'CraftEye' and all(x['sha256'] for x in manifest['implementation'])


def scoring_and_responsive_feedback(page):
    configure(page, 'simulate-crack')
    upload(page)
    start(page)
    expect(page.locator('.st-key-image-ai .is-complete')).to_be_visible(timeout=60000)
    score = page.locator('.st-key-image-ai [data-weld-score]')
    assert int(score.get_attribute('data-weld-score')) <= 59
    expect(page.locator('.st-key-image-ai .analysis-status-only')).to_contain_text('不符合')
    for width, height in [(800,450),(1024,600),(1280,720),(1366,768),(1920,1080)]:
        page.set_viewport_size({'width':width,'height':height})
        for view in ('六维评分','改进建议'):
            page.locator('.st-key-image-ai').get_by_text(view, exact=True).click()
            expect(page.locator('.st-key-image-ai ' + ('.radar-card' if view == '六维评分' else '.feedback-card'))).to_be_visible()
            stable_panel(page)
            bounds = page.locator('.st-key-image-ai .teaching-report').bounding_box()
            assert bounds['y']+bounds['height'] <= height, (width,height,view,bounds)
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(OUT/f'feedback-{width}x{height}.png'))
    page.set_viewport_size({'width':1366,'height':768})
    configure(page, 'simulate-partial')
    page.locator('.st-key-image-ai').get_by_role('button', name='综合分析当前图片', exact=True).click()
    expect(page.locator('.st-key-image-ai .is-complete')).to_be_visible(timeout=30000)
    page.locator('.st-key-image-ai').get_by_text('六维评分',exact=True).click()
    expect(page.locator('.st-key-image-ai .dimension-formula')).to_contain_text('可见项参考分')
    assert 'null' not in page.locator('.st-key-image-ai').inner_text()


def browse_and_invalid_upload(page):
    page.get_by_role('tab', name='浏览数据与标注', exact=True).click()
    expect(page.locator('.st-key-browse-image img')).to_be_visible()
    field = page.get_by_role('spinbutton', name='图片序号')
    field.fill('1619'); field.press('Enter')
    expect(page.get_by_test_id('stException')).to_have_count(0)
    page.get_by_role('combobox').click()
    page.get_by_role('option', name='测试集', exact=True).click()
    expect(field).to_have_attribute('max', '126')
    expect(page.locator('.st-key-browse-image img')).to_be_visible()
    assert int(field.input_value()) <= 126
    page.get_by_role('tab', name='图片识别', exact=True).click()
    page.get_by_role('button', name='选择图片', exact=True).click()
    page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(
        {'name': 'broken.png', 'mimeType': 'image/png', 'buffer': b'not an image'})
    close_popover(page)
    expect(page.get_by_text('图片读取或处理失败：', exact=False)).to_be_visible()
    expect(page.get_by_test_id('stException')).to_have_count(0)
    upload(page)
    start(page)
    expect(page.locator('.st-key-image-stage .detection-summary')).to_be_visible(timeout=60000)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        for test in (no_key_keeps_layout, clear_during_analysis_recovers, error_and_retry, browse_and_invalid_upload, engineering_evidence, scoring_and_responsive_feedback):
            page = browser.new_page(viewport={'width': 1366, 'height': 768})
            try:
                page.goto(URL)
                expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
                test(page)
                results[test.__name__] = 'passed'
            except Exception as exc:
                results[test.__name__] = str(exc)
            page.screenshot(path=str(OUT / (test.__name__ + '.png')))
            page.close()
            print(test.__name__, results[test.__name__], flush=True)
        browser.close()
    (OUT / 'system-regression.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    assert all(value == 'passed' for value in results.values()), results


if __name__ == '__main__':
    main()
