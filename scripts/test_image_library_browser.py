from pathlib import Path
import sys
import json
from PIL import Image
from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from recognition_history import save_record,delete_records,load_picker_records
OUT=ROOT/'outputs/image-library-check'
DB=ROOT/'outputs/ai-check/history-test.sqlite3'
first=ROOT/'assets/weld-examples/uniform.jpg'
image=Image.open(first).convert('RGB')
report={'generated_at':'2026-11-10T22:00:00+08:00','score':{'分数':90,'理由':'测试记录'},'sections':{'缺陷类型':['历史图片预览测试'],'改良建议':['测试建议']}}
delete_records(['picker-new','picker-old'],DB)
save_record('picker-old','image',report,DB,annotated=image)
save_record('picker-new','image',report,DB,annotated=image,original=image)
requests=ROOT/'outputs/ai-check/requests.jsonl'
before=requests.read_bytes() if requests.exists() else b''
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1366,'height':768})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    labels={"example:"+x["id"]:"示例 · "+x["label"] for x in json.loads((ROOT/'assets/weld-examples/examples.json').read_text(encoding='utf-8'))}
    history={"history:"+x["run_id"]:f'历史 #{x["sequence"]} ·' for x in load_picker_records(DB)}
    def tile(key):
        label=labels.get(key,history.get(key))
        return page.locator('.st-key-image-gallery button:visible').filter(has=page.locator('img[alt^='+json.dumps(label,ensure_ascii=False)+']'))
    try:
        page.goto('http://127.0.0.1:8514')
        expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
        page.get_by_role('button',name='选择图片',exact=True).click()
        gallery=page.locator('.st-key-image-gallery')
        expect(page.get_by_test_id('stSelectbox')).to_have_count(0)
        for key in ['uniform','pipe','crack','porosity']:
            expect(tile('example:'+key)).to_be_visible()
            assert tile('example:'+key).locator('img').first.evaluate('(el)=>el.complete&&el.naturalWidth>0')
        assert '.jpg' not in gallery.inner_text()
        for width,height in [(1280,720),(1366,768),(1920,1080)]:
            page.set_viewport_size({'width':width,'height':height})
            page.wait_for_timeout(200)
            box=gallery.bounding_box()
            assert box['y']+box['height']<=height,box
            page.screenshot(path=str(OUT/f'gallery-{width}.png'))
        tile('example:crack').click()
        expect(tile('example:crack')).to_have_attribute('kind','primary')
        page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(first))
        expect(tile('example:crack')).to_have_attribute('kind','secondary')
        for key in ['spatter','irregular','speed','burn-through']:
            expect(tile('example:'+key)).to_be_visible()
        tile('example:burn-through').click()
        expect(tile('example:burn-through')).to_have_attribute('kind','primary')
        expect(gallery.locator('button:visible').filter(has=page.locator('img'))).to_have_count(20)
        expect(gallery.get_by_role('button',name='下一页',exact=True)).to_have_count(0)
        expect(page.get_by_test_id('stExpander')).to_have_count(0)
        gallery.hover()
        page.mouse.wheel(0,1800)
        page.wait_for_timeout(400)
        assert gallery.evaluate('(el)=>{let p=el;while(p){if(p.scrollTop>0)return true;p=p.parentElement;}return [...el.querySelectorAll("*")].some(e=>e.scrollTop>0)}')
        tile('example:rough').scroll_into_view_if_needed()
        tile('example:rough').click()
        expect(tile('example:rough')).to_have_attribute('kind','primary')
        page.get_by_text('历史图片',exact=True).click()
        expect(tile('history:picker-new')).to_be_visible()
        expect(tile('history:picker-old')).to_be_visible()
        tile('history:picker-new').click()
        expect(tile('history:picker-new')).to_have_attribute('kind','primary')
        page.get_by_text('示例图片',exact=True).click()
        tile('example:uniform').click()
        page.mouse.click(900,35)
        expect(page.get_by_role('button',name='开始识别',exact=True)).to_be_enabled()
        page.get_by_role('button',name='开始识别',exact=True).click()
        expect(page.locator('.detection-summary')).to_be_visible(timeout=60000)
        expect(page.get_by_test_id('stException')).to_have_count(0)
        assert not errors,errors
        assert (requests.read_bytes() if requests.exists() else b'')==before
        print('Thumbnail browsing, 20 examples, wheel scrolling, history, source switching, detection and 3 viewport sizes: passed.')
    except Exception:
        page.screenshot(path=str(OUT/'failure.png'))
        (OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
        raise
    finally:
        browser.close()
        delete_records(['picker-new','picker-old'],DB)
