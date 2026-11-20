from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import tempfile
import io
import sqlite3
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from website.recognition_history import load_records, save_record, load_record_images, delete_records, load_picker_records, load_picker_image, load_record_detail, load_original_images


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
        from website.ai_ui import analyze_and_record
        with patch('website.ai_ui.analyze', return_value=report()), patch('website.ai_ui.save_record') as save:
            result = analyze_and_record('run', 'camera', 'input')
        save.assert_called_once_with('run', 'camera', result, annotated=None, original='input', inputs=None)
        with patch('website.ai_ui.analyze', side_effect=RuntimeError('failed')), patch('website.ai_ui.save_record') as save:
            with self.assertRaises(RuntimeError):
                analyze_and_record('failed', 'image')
        save.assert_not_called()

    def test_storage_failure_preserves_completed_report(self):
        from website.ai_ui import analyze_and_record
        with patch('website.ai_ui.analyze', return_value=report()), patch('website.ai_ui.save_record', side_effect=OSError('disk full')):
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
        from website.ai_ui import analyze_and_record
        original = Image.new('RGB', (30, 30), 'gray')
        annotated = Image.new('RGB', (30, 30), 'red')
        with patch('website.ai_ui.analyze', return_value=report()), patch('website.ai_ui.save_record') as save:
            result = analyze_and_record('run', 'camera', original, annotated)
        save.assert_called_once_with('run', 'camera', result, annotated=annotated, original=original, inputs=None)

    def test_picker_and_previews_are_original_only(self):
        original=Image.new('RGB',(25,40),'gray')
        annotated=Image.new('RGB',(25,40),'red')
        save_record('old','image',report(),self.path,annotated=annotated)
        save_record('new','image',report(),self.path,annotated=annotated,original=original)
        save_record('no-image','image',report(),self.path)
        rows=load_picker_records(self.path)
        self.assertEqual([r['run_id'] for r in rows],['new'])
        self.assertEqual([r['has_original'] for r in rows],[1])
        self.assertIsNone(load_picker_image('old',self.path))
        self.assertEqual(set(load_original_images(['new','old'],self.path)),{'new'})
        self.assertEqual(Image.open(io.BytesIO(load_original_images(['new'],self.path)['new'])).tobytes(),original.tobytes())
        for key,image in [('new',original)]:
            self.assertEqual(Image.open(io.BytesIO(load_picker_image(key,self.path))).tobytes(),image.tobytes())
        self.assertEqual(Image.open(io.BytesIO(load_record_images(['new'],self.path,full_size=True)['new'])).tobytes(),annotated.tobytes())
        delete_records(['new'],self.path)
        self.assertIsNone(load_picker_image('new',self.path))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM recognition_originals').fetchone()[0],0)

    def test_complete_snapshot_inputs_and_images_survive_reload(self):
        payload=report()
        payload['sections'].update({'图中现象':['局部凹槽'], '可能原因':['行进不稳']})
        payload.update(model='frozen-model',learning_goal='匀速',feedback_version='frozen-v1',
                       focus_regions=[{'box':[1,2,3,4]}])
        inputs={'detections':[{'类别':'缺陷','置信度':.75,'左':1}],
                'manual_observations':['弧光不稳'],'original_size':[25,40],
                'source_id':'original-fingerprint','api_key':'must-not-be-stored'}
        original=Image.new('RGB',(25,40),'blue')
        annotated=Image.new('RGB',(25,40),'red')
        save_record('full','camera',payload,self.path,original=original,annotated=annotated,inputs=inputs)
        save_record('full','camera',report(99),self.path,inputs={'detections':[]})
        detail=load_record_detail('full',self.path)
        self.assertTrue(detail['complete_snapshot'])
        self.assertEqual(detail['analysis']['sections'],payload['sections'])
        self.assertEqual(detail['analysis']['score']['分数'],76)
        self.assertEqual(detail['analysis']['model'],'frozen-model')
        self.assertEqual(detail['inputs']['detections'],inputs['detections'])
        self.assertEqual(detail['inputs']['source_type'],'camera')
        self.assertNotIn(b'must-not-be-stored',self.path.read_bytes())
        self.assertEqual(Image.open(io.BytesIO(detail['original_png'])).tobytes(),original.tobytes())
        self.assertEqual(Image.open(io.BytesIO(detail['annotated_png'])).tobytes(),annotated.tobytes())
        from website.history_ui import detail_archive
        import zipfile,json
        with zipfile.ZipFile(io.BytesIO(detail_archive(detail))) as archive:
            self.assertEqual(set(archive.namelist()),{'report.json','original.png','detection.png'})
            self.assertEqual(json.loads(archive.read('report.json'))['analysis'],detail['analysis'])
        delete_records(['full'],self.path)
        self.assertIsNone(load_record_detail('full',self.path))
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM recognition_reports').fetchone()[0],0)

    def test_legacy_detail_preserves_known_fields_without_fabrication(self):
        save_record('old','image',report(),self.path)
        with closing(sqlite3.connect(self.path)) as connection,connection:
            connection.execute('DROP TABLE recognition_reports')
        detail=load_record_detail('old',self.path)
        self.assertFalse(detail['complete_snapshot'])
        self.assertEqual(detail['analysis']['sections']['缺陷类型'],report()['sections']['缺陷类型'])
        self.assertNotIn('图中现象',detail['analysis']['sections'])
        self.assertNotIn('detections',detail['inputs'])
        self.assertIsNone(detail['original_png'])
        self.assertIsNone(load_record_detail('missing',self.path))

    def test_delete_selected_records_and_images_preserves_others(self):
        image = Image.new('RGB', (20, 20), 'red')
        for run_id in ('keep', 'remove', 'legacy'):
            save_record(run_id, 'image', report(), self.path, annotated=None if run_id == 'legacy' else image)
        self.assertEqual(delete_records([], self.path), 0)
        self.assertEqual(delete_records(['remove', 'legacy', 'remove', 'missing'], self.path), 2)
        self.assertEqual([row['run_id'] for row in load_records(self.path)], ['keep'])
        self.assertEqual(set(load_record_images(['keep', 'remove'], self.path)), {'keep'})
        self.assertEqual(delete_records(['remove'], self.path), 0)
        save_record('new', 'camera', report(), self.path)
        self.assertGreater(load_records(self.path)[-1]['sequence'], 3)

    def test_delete_failure_rolls_back_images_and_records(self):
        save_record('keep', 'image', report(), self.path, annotated=Image.new('RGB', (20, 20)))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON recognition_history BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            delete_records(['keep'], self.path)
        self.assertEqual(len(load_records(self.path)), 1)
        self.assertIn('keep', load_record_images(['keep'], self.path))

    def test_display_numbers_close_gaps_across_table_chart_details_and_export(self):
        import csv
        from website.growth_chart import growth_data
        from website.history_ui import export_csv
        original = Image.new('RGB', (20, 20), 'blue')
        for i in range(8):
            save_record(str(i), 'image', report(70 + i), self.path, original=original)
        before = {r['run_id']: r['sequence'] for r in load_records(self.path)}
        delete_records(['0', '3', '6'], self.path)
        # Idempotent saves can consume database IDs too; neither kind of gap
        # should appear in the user's consecutive record numbers.
        save_record('7', 'image', report(), self.path)
        save_record('new', 'camera', report(95), self.path, original=original)
        rows = load_records(self.path)
        self.assertEqual([r['run_id'] for r in rows], ['1', '2', '4', '5', '7', 'new'])
        self.assertEqual([r['display_sequence'] for r in rows], list(range(1, 7)))
        for row in rows[:-1]:
            self.assertEqual(row['sequence'], before[row['run_id']])
        self.assertEqual([r['display_sequence'] for r in reversed(rows)], [6, 5, 4, 3, 2, 1])
        self.assertEqual([r['记录序号'] for r in growth_data(rows)], list(range(1, 7)))
        exported = list(csv.DictReader(io.StringIO(export_csv(rows).decode('utf-8-sig'))))
        self.assertEqual([int(r['序号']) for r in exported], list(range(1, 7)))
        self.assertEqual([r['display_sequence'] for r in load_picker_records(self.path)], [6, 5, 4, 3, 2, 1])
        for row in rows:
            detail = load_record_detail(row['run_id'], self.path)
            self.assertEqual(detail['display_sequence'], row['display_sequence'])
            self.assertEqual(detail['analysis']['score']['分数'], row['score'])
        delete_records([r['run_id'] for r in rows], self.path)
        save_record('restart', 'image', report(), self.path)
        self.assertEqual(load_records(self.path)[0]['display_sequence'], 1)

    def test_picker_numbers_are_assigned_before_filtering_and_limit(self):
        image = Image.new('RGB', (5, 5))
        save_record('training', 'training', report(), self.path, original=image)
        save_record('no-image', 'image', report(), self.path)
        for i in range(52):
            save_record(str(i), 'image', report(), self.path, original=image)
        picker = load_picker_records(self.path)
        self.assertEqual(len(picker), 50)
        self.assertEqual([r['display_sequence'] for r in picker], list(range(54, 4, -1)))


if __name__ == '__main__':
    unittest.main()
