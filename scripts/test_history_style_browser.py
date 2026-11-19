"""Regression: row deletions and fragment timers must never remove global styles."""
from pathlib import Path
import sys
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recognition_history import save_record, load_records, load_record_images

OUTPUT = ROOT / 'outputs/ai-check'
DB = OUTPUT / 'history-test.sqlite3'


def main():
    DB.unlink(missing_ok=True)
    for index in range(7):
        save_record(f'style-{index}', 'image', {
            'generated_at': '2026-11-10T20:00:00+08:00',
            'score': {'分数': 85, '理由': '模拟记录'},
            'sections': {'缺陷类型': ['疑似咬边：模拟记录'], '改良建议': ['模拟建议']}},
            DB, annotated=Image.new('RGB', (400, 200), 'gray'))
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1366, 'height': 768})
        try:
            page.goto('http://127.0.0.1:8514')
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('tab', name='识别记录', exact=True).click()
            expect(page.locator('[data-record-id]')).to_have_count(5)
            page.evaluate('''() => {
                window.styleFailures = [];
                function check() {
                    const panel = document.querySelector('.st-key-history-table');
                    const logo = document.querySelector('.partner-logo img');
                    if (getComputedStyle(document.documentElement).getPropertyValue('--header-height').trim() !== '78px')
                        window.styleFailures.push('global stylesheet lost');
                    if (panel && getComputedStyle(panel).borderRadius !== '24px')
                        window.styleFailures.push('panel style lost');
                    if (logo && logo.getBoundingClientRect().width > 210)
                        window.styleFailures.push('logo oversized');
                    requestAnimationFrame(check);
                }
                requestAnimationFrame(check);
            }''')
            # First delete on a full page, then repeat to include changing row counts.
            for index in (6, 5, 4):
                page.locator(f'.st-key-history_row_delete_style-{index} button').click()
                expect(page.locator(f'.st-key-history_row_delete_style-{index}')).to_have_count(0)
                page.wait_for_timeout(2500)
                assert page.evaluate('window.styleFailures') == [], page.evaluate('window.styleFailures.slice(0,5)')
                assert not load_record_images([f'style-{index}'], DB)
            assert len(load_records(DB)) == 4
            page.screenshot(path=str(OUTPUT/'history-delete-style-fixed.png'))
            assert page.locator('.st-key-history-table').evaluate('''el => {
                const r=el.getBoundingClientRect();
                return r.bottom<=innerHeight+1 && el.scrollHeight<=el.clientHeight+2;
            }''')
            print('Repeated row deletion, timer refresh, stylesheet and image cleanup: passed.')
        except Exception:
            page.screenshot(path=str(OUTPUT/'history-delete-style-failure.png'))
            raise
        finally:
            browser.close()


if __name__ == '__main__':
    main()
