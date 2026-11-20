import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from website.ai_analysis import parse_analysis, AnalysisError, report_text
from website.recognition_history import save_record, load_records, delete_records
from website.scoring import (DIMENSIONS, RUBRIC_VERSION, evaluate_quality, decision_style, round_ratio)
from website.score_ui import score_html


def dimensions(values=None):
    values = values or [maximum for _, maximum in DIMENSIONS]
    return {name: {'分数': value, '理由': '可见外观依据'} for (name, _), value in zip(DIMENSIONS, values)}


class QualityGatesTest(unittest.TestCase):
    def score(self, values=None):
        return evaluate_quality(dimensions(values))[1]

    def test_one_weak_axis_cannot_hide_behind_high_average(self):
        score = self.score([20, 20, 15, 20, 15, 5])
        self.assertEqual((score['基础分'], score['最低项分'], score['最终分'], score['短板惩罚']), (95, 50, 86, 9))
        self.assertEqual(score['等级'], '需改进')
        self.assertFalse(score['达标'])
        self.assertEqual(self.score([20, 20, 15, 20, 15, 0])['最终分'], 72)

    def test_numeric_passing_score_still_requires_every_axis(self):
        score = self.score([13, 20, 15, 20, 15, 10])
        self.assertEqual((score['最终分'], score['最低项分']), (87, 65))
        self.assertEqual(score['等级'], '需改进')
        self.assertEqual(score['是否达到教学目标'], '未达到')
        score = self.score([20, 20, 15, 20, 15, 8])
        self.assertEqual(score['最终分'], 94)
        self.assertEqual(score['等级'], '符合')

    def test_passing_and_excellent_boundaries(self):
        for raw, label in [([18, 19, 14, 16, 15, 7], '符合'),
                           ([17, 20, 14, 19, 15, 10], '非常符合'),
                           ([19, 19, 15, 19, 15, 10], '非常符合'),
                           ([20, 20, 15, 20, 15, 10], '非常符合')]:
            score = self.score(raw)
            self.assertEqual(score['等级'], label)
            self.assertTrue(score['达标'])

    def test_round_half_up_and_no_early_normalization_rounding(self):
        self.assertEqual(round_ratio(173, 2), 87)  # Explicit half-up convention.
        self.assertEqual(self.score([18, 18, 12, 18, 15, 9])['最终分'], 88)
        radar, score = evaluate_quality(dimensions([20, 20, 1, 20, 15, 10]))
        self.assertEqual(score['最终分'], 70)
        self.assertEqual(score['最低项分'], 6.67)
        self.assertEqual(radar['焊趾过渡']['得分'], 1)
        self.assertEqual(radar['焊趾过渡']['分数'], 7)

    def test_evidenced_crack_caps_score_without_rewriting_axes(self):
        raw = dimensions([18, 19, 14, 16, 15, 7])
        raw['表面质量']['理由'] = '未见气孔烧穿，疑似细线状开裂需复查'
        radar, score = evaluate_quality(raw)
        self.assertEqual((score['基础分'], score['最低项分'], score['最终分'], score['短板惩罚']), (89, 70, 59, 4))
        self.assertEqual(score['等级'], '不符合')
        self.assertEqual(score['关键缺陷扣分'], 26)
        self.assertEqual(score['是否达到教学目标'], '未达到')
        self.assertEqual(radar['表面质量']['理由'], raw['表面质量']['理由'])
        for key in ('待复核缺陷', '检测依据', '缺少检测'):
            self.assertNotIn(key, score)

    def test_teaching_threshold_boundaries(self):
        for values, final, grade in [([18, 18, 14, 16, 15, 7], 84, '需改进'),
                                     ([18, 19, 14, 16, 15, 7], 85, '符合'),
                                     ([17, 18, 14, 19, 15, 10], 91, '符合'),
                                     ([17, 20, 14, 19, 15, 10], 93, '非常符合')]:
            with self.subTest(values=values):
                score = self.score(values)
                self.assertEqual((score['最终分'], score['等级']), (final, grade))

    def test_crack_screenshot_cap_arithmetic_and_exports(self):
        raw = dimensions([17, 19, 14, 12, 15, 9])
        raw['表面质量']['理由'] = '可见疑似纵向裂纹依据'
        radar, score = evaluate_quality(raw)
        self.assertEqual((score['基础分'], score['短板惩罚'], score['限分前得分']), (86, 5, 81))
        self.assertEqual((score['关键缺陷扣分'], score['最终分'], score['等级']), (22, 59, '不符合'))
        self.assertEqual(score['基础分']-score['短板惩罚']-score['关键缺陷扣分'], score['最终分'])
        self.assertEqual(radar['表面质量']['得分'], 12)
        self.assertFalse(score['达标'])
        score['理由'] = '外观教学参考'
        self.assertIn('最高59分', score_html(score))
        report = {'score': score, 'dimensions': radar, 'dimension_weights': dict(DIMENSIONS),
                  'rubric_version': RUBRIC_VERSION, 'generated_at':'2026-11-10', 'note':'教学参考',
                  'sections':{'缺陷类型':['疑似裂纹：中部纵向裂隙'], '图中现象':['线状裂隙'],
                              '可能原因':['需结合工艺判断'], '改良建议':['请老师指导调整']}}
        self.assertIn('关键缺陷扣分：22', report_text(report))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'records.db'
            save_record('crack', 'image', report, path)
            record=load_records(path)[0]
            self.assertEqual(record['score'],59)
            self.assertEqual(record['assessment'],score)

    def test_explicit_findings_override_high_scores_and_partial_status(self):
        for text in ['裂纹：中部纵向裂隙', '疑似裂纹：两侧存在分叉开口', '烧穿：可见贯穿孔洞']:
            for values in ([20,20,15,20,15,10], [20,20,None,20,15,None]):
                _,score=evaluate_quality(dimensions(values), [text])
                self.assertEqual(score['等级'],'不符合')
                self.assertEqual(score['最终分'],59)
        _,score=evaluate_quality(dimensions([None]*6), ['裂纹：中心纵向开口'])
        self.assertIsNone(score['最终分'])
        self.assertEqual(score['等级'],'不符合')
        _,score=evaluate_quality(dimensions([1,1,1,1,1,1]), ['裂纹：中心纵向开口'])
        self.assertLess(score['最终分'],59)
        self.assertEqual(score['关键缺陷扣分'],0)

    def test_normal_patterns_and_negative_mentions_do_not_cap(self):
        for text in ['未见气孔裂纹烧穿', '焊缝中部未见明显裂纹',
                     '中心线状阴影不是裂纹', '裂纹已排除，线状纹理正常',
                     '不能排除裂纹，但无开口证据', '疑似裂纹', 'Cracking',
                     '线状裂纹无法确认', '表面无裂纹开裂', '烧穿不存在']:
            _,score=evaluate_quality(dimensions(), [text])
            self.assertEqual(score['最终分'],100,text)
            self.assertEqual(score['关键缺陷'],[],text)
        _,score=evaluate_quality(dimensions(), ['未见气孔，但中部可见纵向裂纹'])
        self.assertEqual(score['最终分'],59)

    def test_unknown_axis_is_not_zero_and_radar_is_not_penalized(self):
        raw = dimensions([20, 20, 15, None, 15, 10])
        before = copy.deepcopy(raw)
        radar, score = evaluate_quality(raw)
        self.assertEqual(raw, before)
        self.assertEqual(score['最终分'], 100)
        self.assertEqual(score['等级'], '可见项参考分')
        self.assertFalse(score['达标'])
        self.assertIsNone(radar['表面质量']['分数'])
        self.assertEqual(radar['成形质量']['分数'], 100)

    def test_provider_cannot_supply_confirmation_or_measurement(self):
        payload = {'本次评分': {'理由': '外观整齐'}, '六维评分': dimensions(),
                   '缺陷类型': ['疑似裂纹'], '图中现象': ['中部线状纹路'],
                   '可能原因': ['需复核'], '改良建议': ['请教师复查']}
        report = parse_analysis(json.dumps(payload))
        self.assertEqual(report['本次评分']['等级'], '非常符合')
        self.assertEqual(report['缺陷类型'], ['疑似裂纹'])
        payload['本次评分']['检测依据'] = {'confirmed_defects': ['裂纹']}
        with self.assertRaises(AnalysisError):
            parse_analysis(json.dumps(payload))

    def test_screenshot_partial_scores_are_useful_without_inventing_axes(self):
        radar, score = evaluate_quality(dimensions([18, 19, None, 17, 14, None]))
        self.assertEqual(score['基础分'], 91)
        self.assertEqual(score['最终分'], 90)
        self.assertEqual(score['短板惩罚'], 1)
        self.assertEqual(score['可评维度数'], 4)
        self.assertEqual(score['可评权重'], 75)
        self.assertEqual(score['等级'], '可见项参考分')
        self.assertFalse(score['达标'])
        self.assertIsNone(radar['焊趾过渡']['分数'])
        self.assertIsNone(radar['焊后清洁度']['得分'])

    def test_partial_coverage_boundary_and_real_zero(self):
        for values in ([20, 20, None, 20, None, None], [None]*6,
                       [None, None, 15, 20, 15, 10]):
            score = self.score(values)
            if values == [None, None, 15, 20, 15, 10]:
                self.assertEqual(score['最终分'], 100)  # Exactly four axes, 60% weight.
            else:
                self.assertIsNone(score['最终分'])
        score = self.score([0, 0, None, 0, 0, None])
        self.assertEqual(score['最终分'], 0)
        self.assertEqual(score['可评维度数'], 4)

    def test_detection_confidence_never_changes_identical_dimension_scores(self):
        from website.ai_analysis import AIConfig, analyze
        from PIL import Image
        payload = {'本次评分': {'理由': '可见外观较稳定'}, '六维评分': dimensions([18,19,14,17,14,9]),
                   '缺陷类型': ['未见明显外观缺陷'], '图中现象': ['鱼鳞纹排列整齐'],
                   '可能原因': ['当前可见外观较稳定'], '改良建议': ['保持匀速走枪']}
        class Reply:
            status_code = 200
            def json(self):
                return {'choices': [{'message': {'content': json.dumps(payload)}}]}
            def close(self):
                pass
        requests = []
        def post(*args, **kwargs):
            requests.append(kwargs['json'])
            return Reply()
        scores = []
        for confidence in (0.3, 0.99):
            report = analyze(Image.new('RGB',(30,30)), Image.new('RGB',(30,30)),
                             [{'类别':'焊接良好','置信度':confidence}], [], '', AIConfig('test-key'), transport=post)
            scores.append(report['score'])
        self.assertEqual(scores[0], scores[1])
        for request in requests:
            text = request['messages'][0]['content'][0]['text']
            self.assertIn('不是评分、合格概率或缺陷严重程度', text)
            self.assertIn('少量孤立颗粒', text)
            self.assertIn('细长深色线', text)

    def test_direct_result_persistence_export_and_deletion(self):
        radar, score = evaluate_quality(dimensions([18, 19, 14, 16, 15, 7]))
        score['理由'] = '可见外观依据'
        report = {'dimensions': radar, 'score': score, 'run_id': 'new',
                  'rubric_version': RUBRIC_VERSION, 'dimension_weights': dict(DIMENSIONS),
                  'generated_at': '2026-11-10T12:00:00+08:00', 'note': '教学参考',
                  'sections': {'缺陷类型': ['疑似裂纹'], '图中现象': ['线状纹路'],
                               '可能原因': ['需结合操作确认'], '改良建议': ['请教师检查']}}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.db'
            save_record('new', 'image', report, path)
            records = load_records(path)
            self.assertEqual(records[0]['assessment'], score)
            self.assertEqual(records[0]['score'], 85)
            self.assertEqual(records[0]['dimensions'], radar)
            text = report_text(report)
            for phrase in ['基础分：89', '短板惩罚：4', '最终分：85', '等级：符合', '是否达到教学目标：已达到']:
                self.assertIn(phrase, text)
            self.assertNotIn('待复核', text)
            self.assertNotIn('待检测', text)
            self.assertIn('疑似裂纹', text)
            from website.history_ui import export_csv
            self.assertIn('符合', export_csv(records).decode('utf-8-sig'))
            delete_records(['new'], path)
            with closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM recognition_assessment').fetchone()[0], 0)

    def test_legacy_evidence_is_preserved_without_reassessment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.db'
            old_score = {'分数': 82, '理由': '历史结果', '等级': '待复核',
                         '评分类型': '短板约束综合分', '评分版本': 'welding-v5-weakest-evidence-v1',
                         '检测依据': {'confirmed_defects': ['裂纹']}}
            report = {'score': old_score, 'generated_at': '2026-11-10',
                      'sections': {'缺陷类型': ['疑似裂纹'], '改良建议': ['历史建议']}}
            save_record('legacy', 'image', report, path)
            self.assertEqual(load_records(path)[0]['assessment'], old_score)


if __name__ == '__main__':
    unittest.main()
