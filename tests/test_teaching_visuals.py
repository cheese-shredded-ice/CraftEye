import unittest

from PIL import Image

from defect_references import REFERENCES, REFERENCE_DIR, matched_references
from score_ui import score_band, score_html


class TeachingVisualsTest(unittest.TestCase):
    def test_matches_declared_types_without_matching_negative_evidence(self):
        self.assertEqual(matched_references(['疑似气孔：多个小孔，未见裂纹。', '疑似咬边：边缘凹槽。']), ['气孔', '咬边'])
        self.assertEqual(matched_references(['未见明显外观缺陷：未发现气孔。', '无法判断：无法确认裂纹。']), [])
        self.assertEqual(matched_references(['疑似焊缝成形不良：未见气孔。', '疑似其他外观异常：表面残留。']), [])
        self.assertEqual(matched_references(['疑似气孔：小孔。', '疑似气孔: 孔洞。']), ['气孔'])

    def test_nine_reference_images_are_bundled(self):
        self.assertEqual(len(REFERENCES), 9)
        for name, (filename, _) in REFERENCES.items():
            with self.subTest(name=name), Image.open(REFERENCE_DIR / filename) as image:
                image.verify()
            self.assertEqual(matched_references([f'疑似{name}：可见依据。']), [name])

    def test_score_boundaries_unscorable_and_html_escape(self):
        for value, color in [(0, '#dc2626'), (59, '#dc2626'), (60, '#b45309'), (79, '#b45309'),
                             (80, '#15803d'), (100, '#15803d'), (None, '#64748b')]:
            self.assertEqual(score_band(value)[0], color)
        html = score_html({'分数': None, '理由': '<img src=x onerror=alert(1)>'})
        self.assertIn('暂无法评分', html)
        self.assertIn('data-weld-score="—"', html)
        self.assertNotIn('<img', html)
        self.assertIn('&lt;img', html)


if __name__ == '__main__':
    unittest.main()
