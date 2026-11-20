"""History v3: real storage, row geometry, detail snapshots, deletion, originals."""
import base64
from contextlib import closing
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import zipfile
from PIL import Image
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from recognition_history import save_record,load_records,load_record_detail,load_original_images,load_picker_records
from ai_analysis import parse_analysis
from scoring import DIMENSIONS,RUBRIC_VERSION
DB=ROOT/'outputs/ai-check/history-test.sqlite3'
OUT=ROOT/'outputs/history-detail-check'

def seed():
 DB.unlink(missing_ok=True)
 original=Image.new('RGB',(400,240),(80,120,140))
 annotated=Image.new('RGB',(400,240),'red')
 sections=parse_analysis(json.dumps({'本次评分':{'理由':'保持匀速'},'六维评分':{name:{'分数':weight,'理由':'焊道连续且边缘过渡较均匀。'} for name,weight in DIMENSIONS},'缺陷类型':['未见明显缺陷：这是当时保存的完整缺陷描述。'],'图中现象':['这是当时保存的完整现象，中部纹路连续。'],'可能原因':['走枪节奏较稳定。'],'改良建议':['继续保持稳定电弧和均匀走枪。']}))
 for i in range(7):
  report={'generated_at':f'2026-11-13T10:0{i}:00+08:00','score':sections['本次评分'],
          'dimensions':sections['六维评分'],'rubric_version':RUBRIC_VERSION,'dimension_weights':dict(DIMENSIONS),
          'sections':{k:sections[k] for k in ['缺陷类型','图中现象','可能原因','改良建议']},'model':'saved-model-v3','learning_goal':'保持匀速','feedback_version':'saved-prompt-version'}
  report['sections']['缺陷类型']=['疑似裂纹、未见明显咬边、气孔或烧穿、飞溅较少、不构成飞溅过多：这是长标题测试。']
  save_record(f'history-detail-{i}','camera' if i%2 else 'image',report,DB,
              original=original if i else None,annotated=annotated,
              inputs={'source_id':'original-fingerprint','source_type':'image','original_size':[400,240],
                      'detections':[{'类别':'缺陷','置信度':.81,'左':10,'上':20,'右':100,'下':80}],
                      'manual_observations':['弧光稳定'],'learning_goal':'保持匀速'})
 with closing(sqlite3.connect(DB)) as connection,connection:
  connection.execute("DELETE FROM recognition_reports WHERE run_id='history-detail-0'")

def geometry(page):
 result=page.evaluate("""()=>{
  const box=e=>e.getBoundingClientRect().toJSON();
  const panel=document.querySelector('.st-key-history-table');
  return {panel:box(panel),next:box(panel.querySelector('.st-key-history_next')),
   rows:[...panel.querySelectorAll('[class*="st-key-history-entry-"]')].map(e=>({rect:box(e),cells:box(e.querySelector('.history-record-cells')),buttons:[...e.querySelectorAll('button')].map(box)})),
   bodyWidth:document.body.scrollWidth,bodyHeight:document.body.scrollHeight};
 }""")
 w,h=page.viewport_size.values()
 assert result['panel']['bottom']<=h+1,result
 assert result['next']['bottom']<=h+1,result
 assert result['bodyWidth']<=w and result['bodyHeight']<=h,result
 for row in result['rows']:
  assert len(row['buttons'])==2,row
  for button in row['buttons']:
   assert button['y']>=row['rect']['y']-1 and button['bottom']<=row['rect']['bottom']+1,row
  center=(row['buttons'][0]['y']+row['buttons'][1]['bottom'])/2
  assert abs(center-(row['rect']['y']+row['rect']['bottom'])/2)<4,row
  assert row['cells']['bottom']<=row['rect']['bottom']+1,row

def main():
 OUT.mkdir(exist_ok=True);seed()
 with sync_playwright() as p:
  browser=p.chromium.launch(channel='msedge',headless=True)
  page=browser.new_page(viewport={'width':1366,'height':768},accept_downloads=True)
  errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
  try:
   page.goto(os.environ.get('CRAFTEYE_TEST_URL','http://127.0.0.1:8514'))
   expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
   page.get_by_role('tab',name='识别记录',exact=True).click()
   rows=page.locator('[data-record-id]')
   expect(rows).to_have_count(5)
   expect(rows.first.locator('span').first).to_have_text('7')
   for w,h in [(800,450),(1024,600),(1093,614),(1280,720),(1366,768),(1920,1080)]:
    page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(300)
    geometry(page);page.screenshot(path=str(OUT/f'v3-history-{w}.png'))
   page.set_viewport_size({'width':1024,'height':600})
   page.get_by_role('button',name='详情',exact=True).first.click()
   dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
   expect(dialog.get_by_text('第 7 次识别',exact=True)).to_be_visible()
   page.wait_for_timeout(2500);expect(dialog).to_be_visible()
   expect(dialog.get_by_text('这是当时保存的完整现象，中部纹路连续。',exact=True)).to_be_attached()
   expect(dialog.locator('.radar-image')).to_be_attached()
   page.screenshot(path=str(OUT/'v3-detail.png'))
   with page.expect_download() as downloaded:dialog.get_by_role('button',name='下载本次完整记录',exact=True).click()
   downloaded.value.save_as(OUT/'record.zip')
   with zipfile.ZipFile(OUT/'record.zip') as archive:
    saved=json.loads(archive.read('report.json'))
    assert saved['analysis']['model']=='saved-model-v3'
    assert saved['analysis']['sections']['图中现象']==['这是当时保存的完整现象，中部纹路连续。']
    assert saved['inputs']['detections'][0]['置信度']==.81
    assert Image.open(io.BytesIO(archive.read('original.png'))).getpixel((10,10))==(80,120,140)
    assert Image.open(io.BytesIO(archive.read('detection.png'))).getpixel((10,10))==(255,0,0)
   dialog.get_by_role('button',name='关闭详情',exact=True).click();expect(dialog).not_to_be_visible()
   # Pagination and legacy partial details are kept, not replaced by invented results.
   page.get_by_role('button',name='下一页',exact=True).click();expect(rows).to_have_count(2)
   page.locator('.st-key-history_row_detail_history-detail-0 button').click()
   expect(dialog.get_by_text('旧版本未保存完整报告，以下仅显示当时已保存的内容。',exact=True)).to_be_visible()
   expect(dialog.get_by_text('此记录未保存原图。',exact=True)).to_be_attached()
   dialog.get_by_role('button',name='关闭详情',exact=True).click()
   page.locator('.st-key-history_row_delete_history-detail-0 button').click();expect(rows).to_have_count(1)
   page.locator('.st-key-history_row_delete_history-detail-1 button').click();expect(rows).to_have_count(5)
   expect(page.get_by_role('button',name='下一页',exact=True)).to_be_disabled()
   assert load_record_detail('history-detail-1',DB) is None
   assert len(load_records(DB))==5
   geometry(page)
   # Gallery previews must be the original pixels, not detection-image thumbnails.
   page.get_by_role('tab',name='图片识别',exact=True).click()
   page.get_by_role('button',name='选择图片',exact=True).click()
   page.get_by_text('历史图片',exact=True).click()
   images=page.locator('.st-key-image-gallery img:visible')
   expect(images).to_have_count(5)
   for image in images.all():
    data=base64.b64decode(image.get_attribute('src').split(',')[1])
    pixel=Image.open(io.BytesIO(data)).getpixel((10,10))
    assert all(abs(a-b)<=3 for a,b in zip(pixel,(80,120,140))),pixel
   page.screenshot(path=str(OUT/'v3-original-gallery.png'))
   page.mouse.click(900,35)
   page.get_by_role('tab',name='识别记录',exact=True).click()
   # The deleted record and full snapshot stay deleted after reload.
   page.reload();expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
   page.get_by_role('tab',name='识别记录',exact=True).click();expect(rows).to_have_count(5)
   with page.expect_download() as downloaded:page.get_by_role('button',name='导出记录',exact=True).click()
   downloaded.value.save_as(OUT/'history.csv')
   assert len((OUT/'history.csv').read_text(encoding='utf-8-sig').splitlines())==6
   # Batch deletion remains usable with the new rows and full snapshots.
   page.locator('.st-key-history_bulk_delete button').click()
   selection=page.locator('[data-testid="stMultiSelect"] input:visible').last
   for record in load_records(DB):
    label=f'第{record["display_sequence"]}次'
    selection.fill(label);page.get_by_role('option').filter(has_text=label+' ·').click()
   page.get_by_role('dialog').get_by_text('删除识别记录',exact=True).click()
   page.get_by_role('button',name='删除所选记录',exact=True).click()
   expect(page.get_by_text('暂无记录',exact=False)).to_be_visible(timeout=15000)
   assert load_records(DB)==[]
   with closing(sqlite3.connect(DB)) as c:
    for table in ['recognition_reports','recognition_originals','recognition_images','recognition_scoring','recognition_assessment']:
     assert c.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]==0,table
   assert not errors,errors
   expect(page.get_by_test_id('stException')).to_have_count(0)
   result={'six_viewport_row_alignment':'passed','full_detail_download':'passed','original_pixels_gallery':'passed','legacy_partial_details':'passed','stable_dialog':'passed','paging_delete_reload':'passed','bulk_delete_atomic_cleanup':'passed'}
   (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
  except Exception:
   page.screenshot(path=str(OUT/'failure.png'));(OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8');raise
  finally:browser.close()

if __name__=='__main__':main()
