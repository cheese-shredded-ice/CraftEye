"""Expert presentation regression, isolated DB and mocked cloud transport only."""
import json
import os
from pathlib import Path
import sys
import zipfile
import traceback
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from website.ai_analysis import make_payload, parse_analysis
from website.analysis_audit import build_audit
from website.scoring import DIMENSIONS, RUBRIC_VERSION
from website.recognition_history import save_record, load_records
from test_ai_browser import assert_single_screen

OUT = ROOT / 'outputs/expert-review-check'
DB = ROOT / 'outputs/ai-check/history-test.sqlite3'
REQUESTS = ROOT / 'outputs/ai-check/requests.jsonl'


def seed_growth():
    DB.unlink(missing_ok=True)
    original = Image.new('RGB', (400, 240), (80, 120, 140))
    for i, values in enumerate(([6,6,5,6,5,3], [12,12,9,12,9,6], [18,18,14,18,14,9],
                               [14,14,10,14,10,7], [None]*6, [19,19,15,19,15,10])):
        parsed = parse_analysis(json.dumps({'本次评分':{'理由':'模拟：验证展示流程'},
            '六维评分':{name:{'分数':value,'理由':'模拟：可见图像依据' if value is not None else '模拟：遮挡不可评'}
                        for (name,_),value in zip(DIMENSIONS,values)},
            '缺陷类型':['未见明显裂纹（模拟）'], '图中现象':['焊道连续（模拟）'],
            '可能原因':['节奏稳定（模拟）'], '改良建议':['保持匀速（模拟）']}))
        report = {'generated_at':f'2026-11-19T10:0{i}:00+08:00','score':parsed['本次评分'],
                  'dimensions':parsed['六维评分'],'rubric_version':RUBRIC_VERSION,
                  'dimension_weights':dict(DIMENSIONS),'focus_regions':[],
                  'sections':{k:parsed[k] for k in ['缺陷类型','图中现象','可能原因','改良建议']},
                  'learning_goal':'模拟：基础成形','model':'test-model','provider':'模拟服务'}
        payload = make_payload(original,original,[],[],'','test-model')
        report['audit'] = build_audit(report,payload,original.size,[])
        save_record(f'expert-{i}','image',report,DB,original=original,annotated=original,
                    inputs={'original_size':[400,240],'detections':[],'source_type':'image'})
    return load_records(DB)


def assert_history_fit(page):
    failures=page.evaluate('''() => {
      const failures=[];
      for (const selector of ['html','body','[data-testid="stMain"]','.st-key-history-growth']) {
        const el=document.querySelector(selector), r=el.getBoundingClientRect();
        if(r.bottom>innerHeight+1||r.right>innerWidth+1||el.scrollHeight>el.clientHeight+2||el.scrollWidth>el.clientWidth+2)
          failures.push([selector,r.toJSON(),el.scrollHeight,el.clientHeight]);
      }
      for (const selector of ['.growth-caption','.growth-legend','.training-trend']) {
        const el=document.querySelector(selector), r=el.getBoundingClientRect();
        if(r.bottom>innerHeight+1||r.height<8) failures.push([selector,r.toJSON()]);
      }
      const chart=document.querySelector('[data-testid="stVegaLiteChart"]');
      const graphic=chart.querySelector('.chart-wrapper>svg,canvas');
      if(!graphic) failures.push('missing rendered chart');
      else if(graphic.getBoundingClientRect().bottom>chart.getBoundingClientRect().bottom+2||graphic.getBoundingClientRect().right>chart.getBoundingClientRect().right+2) failures.push('chart axis clipped');
      const labels=[...chart.querySelectorAll('.role-axis-label text')];
      const minimumFont=innerWidth>=1800?18:12;
      if(!labels.length||labels.some(el=>parseFloat(getComputedStyle(el).fontSize)<minimumFont)) failures.push('chart axis labels too small');
      const heading=document.querySelector('.st-key-history-growth h3').getBoundingClientRect();
      const stats=document.querySelector('.history-stats').getBoundingClientRect();
      if(heading.bottom>stats.top+1) failures.push('growth heading overlaps statistics');
      return failures;
    }''')
    assert not failures, failures


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'result.json').unlink(missing_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1366,'height':768},accept_downloads=True)
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            page.goto(os.environ.get('CRAFTEYE_TEST_URL','http://127.0.0.1:8514'))
            expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            expect(page.get_by_role('tab',name='实训行为',exact=True)).to_have_count(0)
            page.get_by_role('button',name='设置',exact=True).click()
            page.get_by_text('分析设置',exact=True).click()
            page.get_by_label('API Key',exact=True).fill('test-key-not-real')
            page.get_by_label('API Key',exact=True).press('Tab')
            page.mouse.click(900,35)
            page.get_by_role('button',name='选择图片',exact=True).click()
            sample=next((ROOT/'dataset/test/images').glob('bad_weld_vid280*'))
            page.get_by_test_id('stFileUploader').locator('input[type=file]').set_input_files(str(sample))
            expect(page.get_by_role('button',name='开始识别',exact=True)).to_be_enabled(timeout=30000)
            page.mouse.click(900,35)
            page.get_by_role('button',name='开始识别',exact=True).click()
            expect(page.locator('.st-key-image-ai .radar-image')).to_be_visible(timeout=60000)
            page.wait_for_timeout(1200)
            audit=page.locator('.st-key-image-ai .analysis-audit')
            expect(audit).to_have_count(1)
            assert not audit.evaluate('(el)=>el.open')
            expect(page.locator('[data-teaching-goal="未达到"]')).to_be_visible()
            for w,h in [(800,450),(1024,600),(1366,768),(1920,1080)]:
                page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(200)
                assert_single_screen(page,'.st-key-image-stage','.st-key-image-ai')
                page.screenshot(path=str(OUT/f'conclusions-{w}.png'))
                audit.locator(':scope > summary').click()
                expect(audit.locator('.audit-step')).to_have_count(4)
                assert not any(audit.locator('.audit-step').evaluate_all('(els)=>els.map(el=>el.open)'))
                for i in range(4):
                    step=audit.locator('.audit-step').nth(i)
                    step.locator('summary').click()
                    assert step.evaluate('(el)=>el.open')
                    assert_single_screen(page,'.st-key-image-stage','.st-key-image-ai')
                    if w==1366:
                        step.locator('.audit-step-body').scroll_into_view_if_needed()
                        page.screenshot(path=str(OUT/f'process-stage-{i+1}.png'))
                    step.locator('summary').click()
                audit.locator(':scope > summary').click()
            page.set_viewport_size({'width':1366,'height':768})
            before=len(REQUESTS.read_text().splitlines())
            audit.locator(':scope > summary').click()
            audit.locator('.audit-step').nth(1).locator('summary').click()
            page.wait_for_timeout(3200)
            assert audit.evaluate('(el)=>el.open')
            assert audit.locator('.audit-step').nth(1).evaluate('(el)=>el.open')
            assert len(REQUESTS.read_text().splitlines())==before
            audit.locator(':scope > summary').click()
            page.get_by_role('button',name='下载分析报告',exact=True).click()
            with page.expect_download() as d:
                page.get_by_role('button',name='保存完整分析报告（JSON）',exact=True).click()
            d.value.save_as(OUT/'analysis.json')
            exported=json.loads((OUT/'analysis.json').read_text(encoding='utf-8'))
            assert all(c['passed'] for c in exported['analysis']['audit']['checks'])
            assert exported['analysis']['score']['计算明细']['final']==73
            assert len(exported['analysis']['audit']['images'])==2+len(exported['analysis']['focus_regions'])
            page.mouse.click(900,35)
            page.get_by_role('button',name='设置',exact=True).click()
            page.get_by_role('button',name='技术与验证',exact=True).click()
            dialog=page.get_by_role('dialog');expect(dialog).to_be_visible()
            expect(dialog.locator('.architecture-flow>div')).to_have_count(5)
            expect(dialog.get_by_text('验证与训练来源',exact=True)).to_be_visible()
            for w,h in [(800,450),(1024,600),(1366,768)]:
                page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(150)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUT/f'engineering-{w}.png'))
            dialog.get_by_text('验证与训练来源',exact=True).click()
            expect(dialog.get_by_text('训练记录：当前使用作者公开训练的权重，未在本项目重新训练。',exact=True)).to_be_visible()
            with page.expect_download() as d:dialog.get_by_role('button',name='下载技术证据清单',exact=True).click()
            d.value.save_as(OUT/'engineering.json')
            evidence=json.loads((OUT/'engineering.json').read_text(encoding='utf-8'))
            assert evidence['detector_source']['trained_locally'] is False
            assert all(x['sha256'] for x in evidence['implementation'])
            page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
            # Verify the same audit survives a full historical detail export.
            page.get_by_role('tab',name='识别记录',exact=True).click()
            page.get_by_role('button',name='详情',exact=True).first.click()
            expect(dialog).to_be_visible()
            detail_audit=dialog.locator('.analysis-audit')
            detail_audit.locator(':scope > summary').click()
            expect(detail_audit.locator('.audit-step')).to_have_count(4)
            with page.expect_download() as d:dialog.get_by_role('button',name='下载本次完整记录',exact=True).click()
            d.value.save_as(OUT/'history.zip')
            with zipfile.ZipFile(OUT/'history.zip') as z:
                history=json.loads(z.read('report.json'))
                assert history['analysis']==exported['analysis']
            dialog.get_by_role('button',name='关闭详情',exact=True).click()
            records=seed_growth()
            page.reload();expect(page.locator('[data-test-ready]')).to_be_attached(timeout=60000)
            page.get_by_role('tab',name='识别记录',exact=True).click()
            expect(page.locator('[data-testid="stVegaLiteChart"] .chart-wrapper>svg')).to_be_visible(timeout=30000)
            expect(page.get_by_text('6 条记录逐一对应 · 5 次有效评分 · 横轴为记录序号',exact=True)).to_be_visible()
            assert records[2]['score']>records[3]['score'] and records[4]['score'] is None
            marks=page.locator('[data-testid="stVegaLiteChart"] .mark-symbol path')
            expect(marks).to_have_count(6)
            labels=marks.evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("aria-label"))')
            for record in records:
                matching=[text for text in labels if f'记录ID: {record["run_id"]}' in text]
                assert len(matching)==1,matching
                assert ('状态: 未评分' if record['score'] is None else f'评分: {record["score"]};') in matching[0]
            for w,h in [(800,450),(1024,600),(1366,768),(1920,1080)]:
                page.set_viewport_size({'width':w,'height':h});page.wait_for_timeout(1800)
                assert_history_fit(page)
                page.screenshot(path=str(OUT/f'growth-{w}.png'))
            page.set_viewport_size({'width':1366,'height':768})
            page.locator('.st-key-history_row_delete_expert-5 button').click()
            expect(page.get_by_text('5 条记录逐一对应 · 4 次有效评分 · 横轴为记录序号',exact=True)).to_be_visible()
            assert [r['run_id'] for r in load_records(DB)]==[f'expert-{i}' for i in range(5)]
            expect(marks).to_have_count(5)
            assert_history_fit(page)
            assert not errors, errors
            result={'four_collapsed_stages':True,'conclusions_and_goal_visible':True,
                    'audit_export_and_history_exact':True,'no_rerun_on_disclosure':True,
                    'truthful_engineering_evidence':True,'growth_declines_nulls_deletion':True,
                    'viewports':['800x450','1024x600','1366x768','1920x1080'],'real_api_called':False}
            (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
        except Exception:
            traceback.print_exc()
            page.screenshot(path=str(OUT/'failure.png'),timeout=10000)
            (OUT/'failure.txt').write_text(page.locator('body').inner_text(),encoding='utf-8')
            diagnostic=page.evaluate('''()=>[...document.querySelectorAll('.st-key-image-stage,.st-key-image-ai,.st-key-image-ai .teaching-report,.st-key-history-growth,[data-testid="stVegaLiteChart"]')].map(el=>({class:el.className,height:getComputedStyle(el).height,min:getComputedStyle(el).minHeight,max:getComputedStyle(el).maxHeight,panel:getComputedStyle(el).getPropertyValue('--panel-height'),children:[...el.children].map(c=>({class:c.className,rect:c.getBoundingClientRect().toJSON(),html:c.outerHTML.slice(0,250)}))}))''')
            print(json.dumps(diagnostic,ensure_ascii=False))
            raise
        finally:
            browser.close()


if __name__=='__main__':main()
