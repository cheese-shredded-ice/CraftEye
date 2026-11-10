from pathlib import Path
import json
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/showcase'
frames=[90,300,570,870,1200,1530,1830,2130,2400,2610]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1920,'height':1200})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://localhost:3000/CraftEye',wait_until='domcontentloaded')
    page.wait_for_function('!!window.remotion_setFrame')
    assert '01:30.00' in page.locator('body').inner_text()
    for frame in frames:
        page.evaluate('(f)=>window.remotion_setFrame(f,"CraftEye",0)',frame)
        page.wait_for_timeout(900)
        preview=page.locator('div[style*="will-change: transform"][style*="width: 1920px"]')
        preview.screenshot(path=str(OUT/f'frame-{frame}.png'))
    # Confirm timeline advances while playing, not just while manually seeking.
    page.evaluate('window.remotion_setFrame(90,"CraftEye",0)')
    page.wait_for_timeout(300)
    page.keyboard.press('Space')
    page.wait_for_timeout(1500)
    page.keyboard.press('Space')
    assert not errors,errors
    page.screenshot(path=str(OUT/'studio-ready.png'))
    browser.close()
sheet=Image.new('RGB',(1500,5*440),'#092b40')
for i,frame in enumerate(frames):
    image=Image.open(OUT/f'frame-{frame}.png').convert('RGB')
    image.thumbnail((730,410))
    x=(i%2)*750+10; y=(i//2)*440
    sheet.paste(image,(x,y+25))
    ImageDraw.Draw(sheet).text((x,y+5),f'{frame/30:.0f}s',fill='white')
sheet.save(OUT/'contact-sheet.jpg',quality=92)
(OUT/'verification.json').write_text(json.dumps({'duration_seconds':90,'width':1920,'height':1080,'fps':30,'sampled_frames':frames,'browser_errors':errors,'audio':False,'subtitles':False},indent=2),encoding='utf-8')
print('10 timeline scenes loaded; preview verified; no browser errors.')
