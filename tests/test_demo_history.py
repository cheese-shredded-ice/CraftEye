import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
from PIL import Image
import unittest

from website.demo_history import demo_records, demo_photo, ensure_training_records
from website.growth_chart import growth_chart
from website.history_ui import export_csv
from website.recognition_history import (load_records, load_record_detail, load_original_images,
                                 load_picker_records, save_record, delete_records)


class BundledTrainingHistoryTest(unittest.TestCase):
    def test_demo_photos_are_distinct_dataset_originals(self):
        root = Path(__file__).resolve().parents[1]
        sources = json.loads((root / 'assets/growth-demo/sources.json').read_text(encoding='utf-8'))
        pixels, names = set(), set()
        for record, source in zip(demo_records(), sources, strict=True):
            self.assertEqual((record['sequence'], record['photo'] + '.jpg'), (source['practice'], source['file']))
            data = demo_photo(record['photo'])
            self.assertEqual(hashlib.sha256(data).hexdigest(), source['sha256'])
            if (root / 'dataset').is_dir() and (root / source['source']).is_file():
                self.assertEqual(data, (root / source['source']).read_bytes())
            with Image.open(io.BytesIO(data)) as im:
                pixels.add(hashlib.sha256(im.convert('RGB').tobytes()).digest())
            names.add(Path(source['source']).name.lower().split('.rf.')[0])
        self.assertEqual((len(names), len(pixels)), (60, 60))

    def test_all_60_records_are_seeded_once_into_the_single_history_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'history.sqlite3'
            self.assertEqual(ensure_training_records(path), 60)
            self.assertEqual(ensure_training_records(path), 0)
            records = load_records(path)
            self.assertEqual(len(records), 60)
            self.assertEqual([record['sequence'] for record in records], list(range(1, 61)))
            self.assertEqual({record['source_type'] for record in records}, {'training'})
            exported = list(csv.DictReader(io.StringIO(export_csv(records).decode('utf-8-sig'))))
            spec = growth_chart(records).to_dict()
            dots = spec['layer'][1].get('data', spec.get('data', {}))['values']
            scores = []
            for n, (record, row, dot) in enumerate(zip(records, exported, dots, strict=True), 1):
                score = record['assessment']['最终分']
                self.assertEqual((n, n, n), (record['sequence'], int(row['序号']), dot['记录序号']))
                self.assertEqual((score,) * 3, (record['score'], int(row['分数']), dot['评分']))
                self.assertEqual(row['来源'], '训练图片')
                self.assertEqual(row['识别时间'], '')
                self.assertNotIn('练习次数', dot)
                self.assertTrue(demo_photo(record['run_id'].replace('training-record-', 'practice-')).startswith(b'\xff\xd8'))
                scores.append(score)
            self.assertEqual(len(scores), 60)
            self.assertEqual(len({r['run_id'] for r in records}), 60)
            stages = [sum(scores[i:i+10]) for i in range(0,60,10)]
            self.assertTrue(all(a < b for a,b in zip(stages,stages[1:])))
            self.assertGreater(scores[-1],scores[0])
            self.assertEqual(len(load_original_images([r['run_id'] for r in records], path)), 60)
            self.assertEqual(load_picker_records(path), [])
            detail = load_record_detail(records[0]['run_id'], path)
            self.assertTrue(detail['complete_snapshot'])
            self.assertEqual(detail['analysis']['dimensions'], records[0]['dimensions'])
            save_record('live-after-training', 'image', {
                'generated_at': '2026-11-20T10:00:00+08:00',
                'score': {'分数': 88, '理由': '训练记录'},
                'sections': {'缺陷类型': [], '改良建议': []}}, path)
            combined = load_records(path)
            self.assertEqual((len(combined), combined[-1]['sequence'], combined[-1]['source_type']),
                             (61, 61, 'image'))
            self.assertEqual(delete_records([r['run_id'] for r in records], path), 60)
            self.assertEqual(ensure_training_records(path), 0)
            self.assertEqual([r['run_id'] for r in load_records(path)], ['live-after-training'])
