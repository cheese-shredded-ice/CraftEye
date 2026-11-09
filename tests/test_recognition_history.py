from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import tempfile
import io
import sqlite3
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from recognition_history import load_records, save_record, load_record_images


def report(score=76):
    return {'generated_at': '2026-11-09T16:00:00+08:00',
            'score': {'分数': score, '理由': '焊道连续，需保持匀速。'},
            'sections': {'缺陷类型': ['疑似咬边：边缘有凹槽。'], '改良建议': ['匀速走枪后比较宽度。']},
            'api_key': 'must-not-be-stored'}


class RecognitionHistoryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'history.sqlite3'

    def tearDown(self):
        self.directory.cleanup()

    def test_persistence_and_unique_runs_including_unscorable(self):
        self.assertEqual(load_records(self.path), [])
        save_record('first', 'image', report(0), self.path)
        save_record('first', 'image', report(99), self.path)
        save_record('second', 'camera', report(None), self.path)
        save_record('third', 'image', report(100), self.path)
        rows = load_records(self.path)
        self.assertEqual([row['score'] for row in rows], [0, None, 100])
        self.assertEqual([row['source_type'] for row in rows], ['image', 'camera', 'image'])
        self.assertEqual(rows[0]['defects'], ['疑似咬边：边缘有凹槽。'])
        self.assertNotIn(b'must-not-be-stored', self.path.read_bytes())

    def test_concurrent_requests_do_not_duplicate_same_run(self):
        load_records(self.path)
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: save_record('same', 'image', report(), self.path), range(12)))
        self.assertEqual(len(load_records(self.path)), 1)

    def test_invalid_scores_are_not_saved(self):
        for score in (True, -1, 101, '80'):
            with self.subTest(score=score), self.assertRaises(ValueError):
                save_record('bad', 'image', report(score), self.path)
        self.assertEqual(load_records(self.path), [])

    def test_completed_request_is_saved_before_ui_consumes_result(self):
        from ai_ui import analyze_and_record
        with patch('ai_ui.analyze', return_value=report()), patch('ai_ui.save_record') as save:
            result = analyze_and_record('run', 'camera', 'input')
        save.assert_called_once_with('run', 'camera', result, annotated=None)
        with patch('ai_ui.analyze', side_effect=RuntimeError('failed')), patch('ai_ui.save_record') as save:
            with self.assertRaises(RuntimeError):
                analyze_and_record('failed', 'image')
        save.assert_not_called()

    def test_storage_failure_preserves_completed_report(self):
        from ai_ui import analyze_and_record
        with patch('ai_ui.analyze', return_value=report()), patch('ai_ui.save_record', side_effect=OSError('disk full')):
            result = analyze_and_record('run', 'image')
        self.assertEqual(result['score']['分数'], 76)
        self.assertTrue(result['history_save_error'])

    def test_annotated_pixels_persist_and_duplicate_does_not_replace_image(self):
        image = Image.new('RGB', (800, 600), 'gray')
        ImageDraw.Draw(image).rectangle((100, 100, 500, 400), outline='red', width=6)
        save_record('picture', 'image', report(), self.path, annotated=image)
        save_record('picture', 'image', report(), self.path, annotated=Image.new('RGB', (10, 10), 'black'))
        full = load_record_images(['picture'], self.path, full_size=True)['picture']
        restored = Image.open(io.BytesIO(full))
        self.assertEqual(restored.size, image.size)
        self.assertEqual(restored.tobytes(), image.tobytes())
        thumbnail = Image.open(io.BytesIO(load_record_images(['picture'], self.path)['picture']))
        self.assertLessEqual(thumbnail.width, 400)
        self.assertLessEqual(thumbnail.height, 240)

    def test_existing_database_keeps_legacy_records_without_inventing_images(self):
        save_record('legacy', 'image', report(), self.path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('DROP TABLE recognition_images')
        self.assertEqual(len(load_records(self.path)), 1)
        self.assertEqual(load_record_images(['legacy'], self.path), {})
        save_record('new', 'camera', report(), self.path, annotated=Image.new('RGB', (20, 20)))
        self.assertEqual(len(load_records(self.path)), 2)
        self.assertEqual(set(load_record_images(['legacy', 'new'], self.path)), {'new'})

    def test_worker_saves_annotated_image_not_original(self):
        from ai_ui import analyze_and_record
        original = Image.new('RGB', (30, 30), 'gray')
        annotated = Image.new('RGB', (30, 30), 'red')
        with patch('ai_ui.analyze', return_value=report()), patch('ai_ui.save_record') as save:
            result = analyze_and_record('run', 'camera', original, annotated)
        save.assert_called_once_with('run', 'camera', result, annotated=annotated)


if __name__ == '__main__':
    unittest.main()
