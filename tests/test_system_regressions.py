"""Boundary cases from the full UI audit; use isolated data only."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_analysis import AIConfig
from ai_ui import detection_report, export_signature
from inference import read_annotation


class ExportTest(unittest.TestCase):
    def test_export_matches_image_observations_and_model_without_key(self):
        config = AIConfig('never-export-this-key', model='test')
        local = {'manual_observations': ['成形不均匀'], 'detections': []}
        completed = {'export_signature': export_signature('image-a', local['manual_observations'], config),
                     'report': {'dimensions': {'成形质量': 80}, 'score': {'分数': 75}}}
        with patch('ai_ui.st.session_state', {'_ai_result_image': completed}), patch('ai_ui.current_config', return_value=config):
            self.assertEqual(detection_report('image', 'image-a', local)['analysis'], completed['report'])
            self.assertNotIn('analysis', detection_report('image', 'image-b', local))
            self.assertNotIn('analysis', detection_report('image', 'image-a', {**local, 'manual_observations': []}))
            self.assertNotIn(config.api_key, str(detection_report('image', 'image-a', local)))
        with patch('ai_ui.st.session_state', {'_ai_result_image': completed}), patch('ai_ui.current_config', return_value=AIConfig('key', model='different')):
            self.assertNotIn('analysis', detection_report('image', 'image-a', local))


class AnnotationTest(unittest.TestCase):
    def test_missing_corrupt_or_unknown_class_is_not_rendered(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'labels.txt'
            with self.assertRaises(OSError):
                read_annotation(path, (100, 100))
            for text in ('0 .5 .5 .2', 'nan .5 .5 .2 .2', '9 .5 .5 .2 .2',
                         '0.5 .5 .5 .2 .2', '0 .5 .5 -1 .2', '0 .5 nan .2 .2'):
                path.write_text(text, encoding='utf-8')
                with self.subTest(text=text), self.assertRaises(ValueError):
                    read_annotation(path, (100, 100))
            path.write_text('\ufeff1 .5 .5 .2 .4\n\n', encoding='utf-8')
            boxes, rows = read_annotation(path, (100, 200))
            self.assertEqual(boxes, [(1, (40, 60, 60, 140), None)])
            self.assertEqual(rows[0]['类别'], '焊接良好')
            path.write_text('', encoding='utf-8')
            self.assertEqual(read_annotation(path, (100, 100)), ([], []))


if __name__ == '__main__':
    unittest.main()
