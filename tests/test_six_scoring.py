import copy
import base64
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from ai_analysis import AnalysisError, parse_analysis
from recognition_history import save_record, load_records, delete_records
from scoring import DIMENSIONS, RUBRIC_VERSION, weighted_score, evaluate_dimensions, round_ratio
from teaching_report_ui import dimensions_html as radar_html


def dimensions_html(dimensions=None):
    html = radar_html(dimensions)
    return base64.b64decode(html.split('base64,')[1].split('"')[0]).decode('utf-8')


class SixScoringTest(unittest.TestCase):
    def setUp(self):
        self.dimensions = {name: {'分数': value, '理由': '可见依据。'}
                           for (name, _), value in zip(DIMENSIONS, [16, 16, 12, 15, 11, 6])}
        self.payload = {'本次评分': {'理由': '先练习边缘衔接。'}, '六维评分': self.dimensions,
                        '缺陷类型': ['疑似咬边：边缘有凹槽。'], '图中现象': ['焊道连续。'],
                        '可能原因': ['走枪可能不稳定。'], '改良建议': ['下次匀速走枪，比较边缘过渡。']}

    def test_raw_scores_normalization_and_full_sum(self):
        self.assertEqual(weighted_score(self.dimensions), 73)
        result = parse_analysis(json.dumps(self.payload))
        self.assertEqual(result['本次评分']['分数'], 73)
        self.assertEqual(result['本次评分']['评分类型'], '短板约束综合分')
        self.assertEqual(result['六维评分']['焊趾过渡']['分数'], 80)
        self.dimensions['焊道走向稳定性']['分数'] = 12
        self.assertEqual(weighted_score(self.dimensions), 74)
        self.assertEqual(evaluate_dimensions(self.dimensions)[2], '短板约束综合分')
        self.assertEqual(round_ratio(7850, 100), 79)

    def test_unobservable_path_does_not_become_zero_or_rescaled_total(self):
        self.dimensions['焊道走向稳定性'] = {'分数': None, '理由': '焊道过于模糊，需补拍'}
        result = parse_analysis(json.dumps(self.payload))
        self.assertEqual(result['本次评分']['分数'], 73)
        self.assertEqual(result['本次评分']['评分类型'], '可见项参考分')
        self.assertEqual(result['六维评分']['成形质量']['得分'], 16)
        self.assertIsNone(result['六维评分']['焊道走向稳定性']['分数'])
        html = dimensions_html(result['六维评分'])
        self.assertIn('—', html)
        self.assertNotIn('class="radar-area"', html)
        self.assertEqual(html.count('class="radar-point"'), 5)

    def test_radar_six_axes_and_real_score_positions(self):
        self.dimensions['焊道走向稳定性']['分数'] = 12
        normalized, _, _ = evaluate_dimensions(self.dimensions)
        html = dimensions_html(normalized)
        self.assertEqual(html.count('class="radar-dimension"'), 6)
        self.assertEqual(html.count('class="radar-point"'), 6)
        self.assertIn('class="radar-area"', html)
        self.assertIn('cx="400.00" cy="95.40"', html)
        self.assertIn('16/20分', html)
        self.assertNotIn('<table', html)
        self.assertNotIn('class="radar-area"', dimensions_html())

    def test_model_cannot_choose_weights_or_total_or_skip_dimension(self):
        for kind in ('total', 'weight', 'missing', 'extra'):
            data = copy.deepcopy(self.payload)
            if kind == 'total':
                data['本次评分']['分数'] = 100
            elif kind == 'weight':
                data['六维评分']['焊道连续性']['权重'] = 100
            elif kind == 'missing':
                del data['六维评分']['焊趾过渡']
            else:
                data['六维评分']['内部质量'] = {'分数': 100, '理由': '猜测'}
            with self.subTest(kind=kind), self.assertRaises(AnalysisError):
                parse_analysis(json.dumps(data))

    def test_scoring_persists_idempotently_with_legacy_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'history.sqlite3'
            report = {'score': {'分数': 79, '理由': '先练习边缘衔接。'},
                      'sections': {key: self.payload[key] for key in ('缺陷类型', '改良建议')},
                      'generated_at': '2026-11-10T16:00:00+08:00'}
            save_record('old', 'image', report, path)
            report.update(dimensions=evaluate_dimensions(self.dimensions)[0], dimension_weights=dict(DIMENSIONS), rubric_version=RUBRIC_VERSION)
            save_record('new', 'image', report, path)
            self.dimensions['焊道连续性']['分数'] = 10
            save_record('new', 'image', report, path)
            old, new = load_records(path)
            self.assertIsNone(old['dimensions'])
            self.assertEqual(new['dimensions']['焊道连续性']['分数'], 80)
            self.assertEqual(new['dimension_weights'], dict(DIMENSIONS))
            self.assertEqual(new['rubric_version'], RUBRIC_VERSION)
            self.assertEqual(new['score_type'], '外观参考分')
            delete_records(['new'], path)
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT count(*) FROM recognition_scoring').fetchone()[0], 0)

    def test_reason_is_html_escaped(self):
        self.dimensions['焊道连续性']['理由'] = '<script>x</script>'
        html = dimensions_html(evaluate_dimensions(self.dimensions)[0])
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)


if __name__ == '__main__':
    unittest.main()
