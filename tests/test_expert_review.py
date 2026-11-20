import copy
import io
import json
import hashlib
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from PIL import Image
from ai_analysis import AIConfig, analyze, make_payload, parse_analysis
from analysis_audit import analysis_status_html, analysis_status_lines, build_audit, audit_html
from engineering_ui import engineering_html, evidence_payload
from growth_chart import growth_data, growth_chart
from scoring import DIMENSIONS, evaluate_quality, round_ratio
from recognition_history import save_record, load_record_detail


def raw(values):
    return {name:{'分数':value,'理由':'可见图像依据'} for (name,_),value in zip(DIMENSIONS,values)}


def record(values):
    axes, score = evaluate_quality(raw(values))
    score['理由']='外观教学评价'
    return {'generated_at':'2026-11-19T10:00:00+08:00','dimensions':axes,'score':score,
            'rubric_version':score['评分版本'],'dimension_weights':dict(DIMENSIONS),'focus_regions':[],
            'sections':{'缺陷类型':['未见明显裂纹'],'图中现象':['焊道连续'],'可能原因':['走枪稳定'],'改良建议':['保持匀速']}}


class ExpertReviewTest(unittest.TestCase):
    def test_analysis_status_bar_exists_for_empty_and_streaming_states(self):
        first, second = analysis_status_lines(empty=True)
        empty_html = analysis_status_html(empty=True)
        self.assertIn(first, empty_html)
        self.assertIn(second, empty_html)
        self.assertIn('analysis-status-light is-idle', empty_html)
        report = {'streaming': True, 'dimensions': {name: {'分数': None} for name, _ in DIMENSIONS}}
        streaming_first, streaming_second = analysis_status_lines(report)
        streaming_html = analysis_status_html(report)
        self.assertIn(streaming_first, streaming_html)
        self.assertIn(streaming_second, streaming_html)
        self.assertIn('analysis-status-light is-analyzing', streaming_html)
        complete_html = analysis_status_html(record([20, 20, 15, 20, 15, 10]))
        self.assertIn('analysis-status-light is-complete', complete_html)

    def test_exact_trace_matches_score_and_no_early_rounding(self):
        for values in ([20,20,1,20,15,10],[20,20,15,20,15,0],[18,19,None,17,14,None],[None]*6):
            report=record(values); c=report['score']['计算明细']
            if c['sufficient']:
                a=Fraction(**c['base_exact']); m=Fraction(**c['minimum_exact'])
                combined=(80*a+20*m)/100
                self.assertEqual(Fraction(**c['combined_exact']),combined)
                self.assertEqual(c['final'],round_ratio(combined.numerator,combined.denominator))
            else:
                self.assertIsNone(c['final'])
                self.assertIsNone(c['base_exact'])
            for (name,maximum),value in zip(DIMENSIONS,values):
                self.assertEqual(report['dimensions'][name]['得分'],value)

    def test_critical_trace_explains_cap_without_axis_mutation(self):
        items=raw([20,20,15,20,15,10])
        axes,score=evaluate_quality(items,['裂纹：中心可见线状开口'])
        self.assertEqual(score['计算明细']['before_cap'],100)
        self.assertEqual(score['计算明细']['final'],59)
        self.assertEqual(score['关键缺陷扣分'],41)
        self.assertTrue(all(item['分数']==100 for item in axes.values()))

    def test_actual_payload_hashes_checks_and_persisted_audit(self):
        image=Image.new('RGB',(500,300),'gray')
        report=record([16,16,12,15,11,6])
        payload=make_payload(image,image,[],[],'','qwen3-vl-plus')
        report['audit']=build_audit(report,payload,image.size,[])
        self.assertTrue(all(x['passed'] for x in report['audit']['checks']))
        self.assertEqual(len(report['audit']['images']),2)
        self.assertEqual(report['audit']['images'][0]['size'],[500,300])
        changed=copy.deepcopy(report);changed['score']['分数']=99
        self.assertFalse(build_audit(changed,payload,image.size,[])['checks'][1]['passed'])
        changed['audit']=build_audit(changed,payload,image.size,[])
        self.assertIn('计算校验发现差异',audit_html(changed))
        with tempfile.TemporaryDirectory() as path:
            db=Path(path)/'test.db'
            save_record('audit','image',report,db,original=image)
            saved=load_record_detail('audit',db)
            self.assertEqual(saved['analysis']['audit'],report['audit'])
            self.assertEqual(saved['analysis']['score']['计算明细'],report['score']['计算明细'])

    def test_default_folded_four_stages_and_escaped_content(self):
        report=record([20,20,15,20,15,10]);report['learning_goal']='<script>bad()</script>'
        html=audit_html(report)
        self.assertEqual(html.count('class="audit-step"'),4)
        self.assertNotIn(' open',html)
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        report['score'].pop('计算明细')
        self.assertIn('不',audit_html(report))
        self.assertIn('旧记录未保存逐步运算快照',audit_html(report))
        missing=audit_html(record([None]*6))
        self.assertIn('均未计算',missing)
        self.assertNotIn('÷ 0',missing)

    def test_growth_all_records_declines_null_gaps_and_rule_changes(self):
        records=[{'sequence':i*2+1,'run_id':str(i),'generated_at':'test','score':x,'rubric_version':v}
                 for i,(x,v) in enumerate([(40,'a'),(90,'a'),(59,'a'),(None,'a'),(95,'a'),(50,'b'),(80,'a')])]
        data=growth_data(records)
        self.assertEqual([x['评分'] for x in data],[40,90,59,None,95,50,80])
        self.assertEqual([x['历次最高'] for x in data],[40,90,90,90,95,50,80])
        self.assertEqual([x['记录序号'] for x in data],[1,3,5,7,9,11,13])
        self.assertNotEqual(data[2]['线段'],data[4]['线段'])
        self.assertNotEqual(data[0]['规则阶段'],data[-1]['规则阶段'])
        growth_chart(records).to_dict()
        growth_chart([dict(records[0],score=None)]).to_dict()
        self.assertEqual(len(growth_data(records*6)),42)
        large=[dict(records[0],sequence=i+1,run_id=str(i)) for i in range(5001)]
        spec=growth_chart(large).to_dict()
        self.assertEqual([layer['mark']['type'] for layer in spec['layer']], ['line','point','point'])
        self.assertNotIn('strokeDash',spec['layer'][0]['mark'])
        points_data=spec['layer'][1].get('data',spec.get('data',{}))
        self.assertEqual(len(points_data['values']),5001)

    def test_provenance_no_fabricated_training_and_no_secrets(self):
        data=evidence_payload();html=engineering_html(data)
        self.assertFalse(data['detector_source']['trained_locally'])
        self.assertIn('未在本项目重新训练',html)
        self.assertIn('不是九类缺陷识别准确率',html)
        self.assertTrue(all(item['sha256'] for item in data['implementation']))
        self.assertNotIn('sk-ws-',json.dumps(data))
        self.assertNotIn('api_key',json.dumps(data))
        root=Path(__file__).resolve().parents[1]
        for source in data['evidence_sources']:
            content=(root/'assets/engineering'/source['copied_file']).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(),source['sha256'])
            # These are immutable historical snapshots. Running a new install
            # check may replace the live source; its old snapshot stays intact.
            self.assertEqual(source['type'], 'historical_local_verification')


if __name__=='__main__':unittest.main()
