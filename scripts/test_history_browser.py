"""Verify history paging/chart/export with isolated synthetic records on port 8502."""
import csv
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path
import sys

from playwright.sync_api import sync_playwright, expect
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recognition_history import save_record, load_records

OUTPUT = ROOT / 'outputs/ai-check'
DB = OUTPUT / 'history-test.sqlite3'


def main():
    DB.unlink(missing_ok=True)
    sample = Image.open(next((ROOT/'dataset/test/images').glob('bad_weld_vid280*'))).convert('RGB')
    ImageDraw.Draw(sample).rectangle((100, 100, 300, 220), outline='red', width=5)
    for index, score in enumerate([0, 42, 55, 60, None, 67, 72, 70, 79, 85, 91, 100]):
        save_record(f'history-fixture-{index}', 'camera' if index % 2 else 'image', {
            'generated_at': (datetime(2026, 11, 9, 10, tzinfo=timezone(timedelta(hours=8))) + timedelta(minutes=index*10)).isoformat(),
            'score': {'分数': score, '理由': '模拟练习记录'},
            'sections': {'缺陷类型': ['疑似未焊透：需查看断面。', '疑似未熔合：需进一步确认。'],
                         '改良建议': ['模拟：保持匀速走枪。']}}, DB, annotated=sample if index > 0 else None)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width':1366, 'height':768}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            page.goto('http://127.0.0.1:8502', wait_until='domcontentloaded')
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('tab', name='识别记录', exact=True).click()
            expect(page.locator('.history-table tbody tr')).to_have_count(5, timeout=15000)
            expect(page.locator('.history-table tbody tr').first.locator('td').first).to_have_text('12')
            expect(page.get_by_role('columnheader', name='检测图片')).to_be_visible()
            expect(page.locator('.history-thumbnail')).to_have_count(5)
            expect(page.locator('[data-testid="stVegaLiteChart"]')).to_be_visible(timeout=15000)
            expect(page.get_by_text('训练趋势总结', exact=True)).to_be_visible()
            expect(page.locator('.training-trend')).to_contain_text('上升 18.3 分')
            expect(page.locator('.training-trend')).to_contain_text('近5次')
            for width, height in ((1280,720),(1366,768),(1920,1080)):
                page.set_viewport_size({'width':width,'height':height})
                page.wait_for_timeout(300)
                failures = page.evaluate('''() => {
                    const failures = [];
                    for (const selector of ['[data-testid="stMain"]','.st-key-history-table','.st-key-history-growth']) {
                        const el = document.querySelector(selector), box = el.getBoundingClientRect();
                        if (box.bottom > innerHeight+1 || box.right > innerWidth+1 || el.scrollHeight > el.clientHeight+2 || el.scrollWidth > el.clientWidth+2)
                            failures.push([selector,box.bottom,el.scrollHeight,el.clientHeight,el.scrollWidth,el.clientWidth]);
                    }
                    return failures;
                }''')
                assert not failures, failures
                dimensions = page.locator('.st-key-history-table').evaluate('''el => {
                    const table = el.querySelector('.history-table').getBoundingClientRect();
                    const panel = el.getBoundingClientRect();
                    const images = [...el.querySelectorAll('.history-thumbnail')];
                    return {gap:panel.bottom-table.bottom, valid:images.every(img => img.complete && img.naturalWidth > 0)};
                }''')
                assert 40 < dimensions['gap'] < 125, dimensions
                assert dimensions['valid']
                page.screenshot(path=str(OUTPUT / f'history-{width}x{height}.png'))
            page.get_by_role('button', name='下一页', exact=True).click()
            expect(page.locator('.history-table tbody tr').first.locator('td').first).to_have_text('7')
            expect(page.locator('.history-table tbody').get_by_text('—', exact=True)).to_be_visible()
            page.get_by_role('button', name='下一页', exact=True).click()
            expect(page.locator('.history-table tbody tr')).to_have_count(2)
            expect(page.get_by_text('暂无图片', exact=True)).to_be_visible()
            expect(page.get_by_role('button', name='下一页', exact=True)).to_be_disabled()
            page.get_by_role('button', name='上一页', exact=True).click()
            expect(page.locator('.history-table tbody tr')).to_have_count(5)
            with page.expect_download() as downloaded:
                page.get_by_role('button', name='导出记录', exact=True).click()
            downloaded.value.save_as(OUTPUT / 'history.csv')
            rows = list(csv.reader(io.StringIO((OUTPUT / 'history.csv').read_text(encoding='utf-8-sig'))))
            assert len(rows) == 13 and rows[5][3] == '暂无法评分'
            assert len(load_records(DB)) == 12
            save_record('trend-refresh', 'image', {
                'generated_at': '2026-11-09T12:30:00+08:00',
                'score': {'分数': 10, '理由': '模拟新记录'},
                'sections': {'缺陷类型': ['疑似咬边：凹槽。'], '改良建议': ['模拟：练习匀速。']}}, DB)
            expect(page.locator('.training-trend')).to_contain_text('下降 11.0 分', timeout=15000)
            assert not errors, errors
            print('History table, pagination, score curve, null/zero scores, CSV export and three desktop sizes: passed.')
        except Exception:
            page.screenshot(path=str(OUTPUT / 'history-failure.png'))
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
