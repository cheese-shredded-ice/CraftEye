import asyncio
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

import av
from PIL import Image

from behavior_core import BehaviorAnalyzer, BehaviorConfig, ppe_evidence, torso_angle
from behavior_video import BehaviorCameraProcessor, VideoJob, inspect_video


def person(box=(20, 10, 180, 190), lean=False, hidden=False):
    pts = [[100., 80., .9] for _ in range(17)]
    for side in (0, 1):
        pts[5+side] = [160 if lean else 100, 60, .1 if hidden else .9]
        pts[11+side] = [100, 100, .1 if hidden else .9]
    return {'box': list(box), 'confidence': .9, 'points': pts}


def gear(name, confidence=.9, box=(80, 40, 120, 90)):
    return {'class': name, 'confidence': confidence, 'box': list(box)}


class BehaviorRulesTest(unittest.TestCase):
    def test_no_detection_is_unknown_not_bad_or_good(self):
        a = BehaviorAnalyzer()
        for t in range(5):
            a.update(t, [], [], [], (200, 200))
        r = a.finish(5)
        self.assertEqual(r['totals']['unknown'], 5)
        self.assertEqual(r['events'], [])
        self.assertIsNone(r['inside_percent'])
        self.assertNotIn('score', r)

    def test_hidden_ppe_and_pose_are_unknown(self):
        a = BehaviorAnalyzer()
        for t in range(4):
            a.update(t, [person(hidden=True)], [], [], (200, 200))
        r = a.finish(4)
        self.assertEqual(r['totals']['pose_observed'], 0)
        self.assertEqual(r['ppe_seconds']['手套']['unseen'], 4)
        self.assertEqual(r['events'], [])

    def test_direct_negative_evidence_is_required(self):
        p = person()
        self.assertEqual(ppe_evidence([gear('avec_casque')], p, .5)['面罩'], 'observed')
        self.assertEqual(ppe_evidence([gear('sans_gants')], p, .5)['手套'], 'missing')
        self.assertEqual(ppe_evidence([gear('sans_gants', .3)], p, .5)['手套'], 'uncertain')
        self.assertEqual(ppe_evidence([gear('sans_gants'), gear('avec_gants', .3)], p, .5)['手套'], 'uncertain')
        self.assertEqual(ppe_evidence([gear('sans_gants', box=(220, 40, 250, 80))], p, .5)['手套'], 'unseen')

    def test_event_debounce_and_durations(self):
        a = BehaviorAnalyzer(BehaviorConfig(min_event_seconds=2))
        for t in [0, .5, 1, 1.5, 2, 2.5, 3]:
            a.update(t, [person(lean=True)], [gear('sans_gants')], [], (200, 200))
        r = a.finish(3.5)
        self.assertEqual({e['type'] for e in r['events']}, {'lean', 'ppe_手套'})
        self.assertTrue(all(e['seconds'] == 3.5 for e in r['events']))
        self.assertAlmostEqual(r['totals']['lean'], 3.5)
        self.assertAlmostEqual(sum(r['ppe_seconds']['手套'].values()), 3.5)

    def test_short_burst_not_an_event(self):
        a = BehaviorAnalyzer()
        for t in [0, .3, .6]:
            a.update(t, [person(lean=True)], [], [], (200, 200))
        a.update(.9, [person()], [], [], (200, 200))
        self.assertEqual(a.finish()['events'], [])

    def test_gap_never_counts_as_outside_or_pose_exposure(self):
        a = BehaviorAnalyzer()
        a.update(0, [person(lean=True)], [], [], (200, 200))
        a.update(20, [person(lean=True)], [], [], (200, 200))
        r = a.finish()
        self.assertEqual(r['totals']['unknown'], 20)
        self.assertEqual(r['totals']['lean'], 0)
        self.assertEqual(r['events'], [])

    def test_people_count_and_jump_invalidate_measurement(self):
        a = BehaviorAnalyzer()
        r = a.update(0, [person(), person()], [gear('sans_gants')], [], (200, 200))
        self.assertEqual(r['latest']['location'], 'unknown')
        a.update(1, [person()], [], [], (400, 200))
        r = a.update(2, [person(box=(250, 10, 390, 190))], [], [], (400, 200))
        self.assertEqual(r['latest']['location'], 'unknown')

    def test_roi_and_observable_time_denominator(self):
        a = BehaviorAnalyzer(BehaviorConfig(roi=(0, 0, .4, 1)))
        for t in range(4):
            a.update(t, [person()], [], [], (200, 200))
        r = a.finish(4)
        self.assertEqual(r['totals']['outside'], 4)
        self.assertEqual(r['inside_percent'], 0)
        self.assertEqual(r['events'][0]['type'], 'outside')

    def test_phone_requires_hand_proximity(self):
        a = BehaviorAnalyzer()
        near = gear('cell phone', box=(95, 75, 105, 85))
        far = gear('cell phone', box=(22, 170, 30, 180))
        self.assertFalse(a.update(0, [person()], [], [far], (200, 200))['latest']['phone'])
        self.assertTrue(a.update(1, [person()], [], [near], (200, 200))['latest']['phone'])

    def test_invalid_time_and_config(self):
        with self.assertRaises(ValueError):
            BehaviorConfig(roi=(.5, 0, .5, 1))
        a = BehaviorAnalyzer()
        a.update(1, [], [], [], (200, 200))
        for t in [1, 0, float('nan')]:
            with self.assertRaises(ValueError):
                a.update(t, [], [], [], (200, 200))


class FakeRunner:
    def detect(self, image):
        return dict(people=[person()], equipment=[], phones=[], elapsed_ms=1.)


class BehaviorMediaTest(unittest.TestCase):
    def test_camera_queued_frame_and_stop(self):
        processor = BehaviorCameraProcessor(BehaviorConfig(), FakeRunner())
        frame = av.VideoFrame.from_image(Image.new('RGB', (200, 200)))
        frame.pts, frame.time_base = 100, Fraction(1, 90000)
        result = asyncio.run(processor.recv_queued([frame, frame]))[0]
        self.assertEqual(result.pts, 100)
        self.assertEqual(processor.snapshot()[0]['samples'], 1)
        before = processor.finish()
        processor.recv(frame)
        self.assertEqual(before, processor.snapshot()[0])

    def test_video_invalid_file_and_job_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'bad.mp4'
            path.write_bytes(b'invalid')
            with self.assertRaises(ValueError):
                inspect_video(path)
            job = VideoJob(path, BehaviorConfig(), tmp, FakeRunner())
            job.run()
            self.assertEqual(job.snapshot()['status'], 'error')
            self.assertFalse((job.root/'report.json').exists())

    def test_encoded_video_duration_report_and_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'source.mp4'
            with av.open(str(path), 'w') as output:
                stream = output.add_stream('libx264', rate=10)
                stream.width = stream.height = 200
                stream.pix_fmt = 'yuv420p'
                for _ in range(30):
                    for packet in stream.encode(av.VideoFrame.from_image(Image.new('RGB', (200, 200)))):
                        output.mux(packet)
                for packet in stream.encode():
                    output.mux(packet)
            job = VideoJob(path, BehaviorConfig(), tmp, FakeRunner())
            job.run()
            self.assertEqual(job.snapshot()['status'], 'done', job.snapshot()['error'])
            report = json.loads((job.root/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['totals']['duration'], 3)
            self.assertEqual(report['sample_count'], 10)
            self.assertAlmostEqual(inspect_video(job.root/'annotated.mp4')['duration'], 3, places=2)
            cancelled = VideoJob(path, BehaviorConfig(), tmp, FakeRunner())
            cancelled.cancel.set()
            cancelled.run()
            self.assertEqual(cancelled.snapshot()['status'], 'cancelled')
            self.assertFalse((cancelled.root/'report.json').exists())


if __name__ == '__main__':
    unittest.main()
