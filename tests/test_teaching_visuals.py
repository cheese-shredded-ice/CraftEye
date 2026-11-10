import unittest

from PIL import Image

from defect_references import REFERENCES, REFERENCE_DIR, matched_references
from score_ui import score_html
from scoring import score_band, progress_band


class TeachingVisualsTest(unittest.TestCase):
    def test_matches_declared_types_without_matching_negative_evidence(self):
        self.assertEqual(matched_references(['疑似气孔：多个小孔，未见裂纹。', '疑似咬边：边缘凹槽。']), ['气孔', '咬边'])
        self.assertEqual(matched_references(['未见明显外观缺陷：未发现气孔。', '无法判断：无法确认裂纹。']), [])
        self.assertEqual(matched_references(['疑似焊缝成形不良：未见气孔。', '疑似其他外观异常：表面残留。']), [])
        self.assertEqual(matched_references(['疑似气孔：小孔。', '疑似气孔: 孔洞。']), ['气孔'])
        self.assertEqual(matched_references(['气孔：表面小孔。', '咬边：边缘凹槽。', '未见裂纹：划痕。']), ['气孔', '咬边'])

    def test_nine_reference_images_are_bundled(self):
        self.assertEqual(len(REFERENCES), 9)
        for name, (filename, _) in REFERENCES.items():
            with self.subTest(name=name), Image.open(REFERENCE_DIR / filename) as image:
                image.verify()
            self.assertEqual(matched_references([f'疑似{name}：可见依据。']), [name])

    def test_score_boundaries_unscorable_and_html_escape(self):
        for value, label in [(0, '严重不符合'), (59, '严重不符合'), (60, '不符合'), (74, '不符合'),
                             (75, '需改进'), (84, '需改进'), (85, '符合'), (92, '符合'),
                             (93, '非常符合'), (100, '非常符合'), (None, '暂无法评分')]:
            self.assertEqual(score_band(value)[1], label)
        for value, label in [(0, '严重不符合'), (19, '严重不符合'), (20, '不符合'), (39, '不符合'),
                             (40, '一般'), (59, '一般'), (60, '符合'), (79, '符合'),
                             (80, '非常符合'), (100, '非常符合'), (None, '暂无法评分')]:
            self.assertEqual(progress_band(value)[1], label)
            html = score_html({'分数': value, '理由': '练习参考', '等级': label})
            if value is None:
                self.assertNotIn('class="score-marker"', html)
                self.assertNotIn('aria-valuenow', html)
            else:
                self.assertIn(f'aria-valuenow="{value}"', html)
                self.assertIn('class="score-marker"', html)
                self.assertIn(f'{label}</span>', html) if value is not None else None
        html = score_html({'分数': None, '理由': '<img src=x onerror=alert(1)>'})
        self.assertIn('暂无法评分', html)
        self.assertIn('data-weld-score="—"', html)
        self.assertNotIn('<img src=x', html)
        self.assertNotIn('score-outcome', html)
        self.assertNotIn('教学目标：', html)

    def test_critical_decision_does_not_replace_numeric_progress_tier(self):
        score = {'分数': 59, '等级': '不符合', '关键缺陷': [{'类型': '裂纹'}],
                 '分数上限': 59, '关键缺陷扣分': 22}
        html = score_html(score)
        self.assertIn('aria-valuetext="59分，一般"', html)
        self.assertIn('裂纹风险：不符合', html)
        self.assertEqual(score['等级'], '不符合')


if __name__ == '__main__':
    unittest.main()
