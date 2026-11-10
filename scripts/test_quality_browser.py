"""Evidence gates, teacher review and exported state; mock API on port 8502 only."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'outputs/ai-check'


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 720}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            page.goto('http://127.0.0.1:8502', wait_until='domcontentloaded')
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('button', name='设置', exact=True).click()
            page.get_by_label('API Key', exact=True).fill('test-key-not-real')
            page.get_by_label('视觉模型', exact=True).fill('simulate-crack')
            page.get_by_label('视觉模型', exact=True).press('Tab')
            page.get_by_role('heading', name='数智评鉴系统', exact=True).click()
            page.get_by_role('button', name='选择图片', exact=True).click()
            sample = next((ROOT/'dataset/test/images').glob('bad_weld_vid280*'))
            page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(sample))
            expect(page.get_by_role('button', name='开始识别', exact=True)).to_be_enabled(timeout=30000)
            page.get_by_role('heading', name='数智评鉴系统', exact=True).click()
            page.get_by_role('button', name='开始识别', exact=True).click()
            expect(page.locator('.score-status')).to_have_text('非常符合', timeout=60000)
            expect(page.locator('[data-weld-score="100"]')).to_be_visible()
            expect(page.get_by_role('button', name='检测复核', exact=True)).to_have_count(0)
            expect(page.locator('.score-outcome')).to_have_count(0)
            for width, height in [(1280, 720), (1366, 768), (1920, 1080)]:
                page.set_viewport_size({'width': width, 'height': height})
                page.wait_for_timeout(200)
                overflow = page.evaluate("""()=>[...document.querySelectorAll('.score-summary,.dimension-review,.st-key-image-ai')].filter(el=>el.scrollHeight>el.clientHeight+2 || el.scrollWidth>el.clientWidth+2).map(el=>el.className)""")
                assert not overflow, overflow
            page.get_by_role('button', name='下载分析报告', exact=True).click()
            with page.expect_download() as download:
                page.get_by_role('button', name='保存完整分析报告（JSON）', exact=True).click()
            download.value.save_as(OUTPUT/'quality-direct.json')
            report = json.loads((OUTPUT/'quality-direct.json').read_text(encoding='utf-8'))['analysis']
            assert report['score']['等级'] == '非常符合'
            assert '检测依据' not in report['score']
            assert report['sections']['缺陷类型'][0].startswith('疑似裂纹')
            with closing(sqlite3.connect(OUTPUT/'history-test.sqlite3')) as db:
                row = db.execute('SELECT score_json FROM recognition_assessment WHERE run_id=?', (report['run_id'],)).fetchone()
                assert json.loads(row[0]) == report['score']
            assert not errors, errors
            print('Direct appearance grade, removed review controls, preserved defect text, export and persistence: passed.')
        except Exception:
            page.screenshot(path=str(OUTPUT/'quality-failure.png'), full_page=True)
            (OUTPUT/'quality-failure.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
