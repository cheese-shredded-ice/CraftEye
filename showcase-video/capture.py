"""Capture actual production UI components and archived data in an isolated app."""
from pathlib import Path
import json
import sqlite3
import shutil
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT/'showcase-video/public'
PUBLIC.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1920,'height':1080}, device_scale_factor=1)
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    boxes={}
    for name, query in [('crack','record=82'),('advice','record=82&view=advice'),('excellent','record=84')]:
        page.goto('http://127.0.0.1:8503/?'+query)
        expect(page.locator('.score-summary')).to_be_visible(timeout=60000)
        page.wait_for_function('Array.from(document.images).every(i=>i.complete)')
        page.wait_for_timeout(700)
        page.screenshot(path=str(PUBLIC/(name+'.png')))
        boxes[name]={s:page.locator(s).bounding_box() for s in ['.score-summary','.st-key-image-stage','.st-key-image-ai']}
    page.get_by_role('tab', name='识别记录', exact=True).click()
    expect(page.locator('.history-table')).to_be_visible(timeout=30000)
    page.wait_for_timeout(1800)
    page.screenshot(path=str(PUBLIC/'history.png'))
    boxes['history']={s:page.locator(s).bounding_box() for s in ['.st-key-history-table','.st-key-history-growth']}
    page.goto('http://127.0.0.1:8501')
    expect(page.get_by_role('heading', name='数智评鉴系统', exact=True)).to_be_visible(timeout=60000)
    page.wait_for_timeout(1000)
    page.screenshot(path=str(PUBLIC/'home.png'))
    assert not errors, errors
    (PUBLIC/'regions.json').write_text(json.dumps(boxes,ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
shutil.copy(ROOT/'assets/dashboard/crafteye-logo.png',PUBLIC/'logo.png')
shutil.copy(ROOT/'assets/dashboard/welding-banner.webp',PUBLIC/'welding.webp')
print('Captured 5 frames from real records and current UI; no cloud API calls.')
