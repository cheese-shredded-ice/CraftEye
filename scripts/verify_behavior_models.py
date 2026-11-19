"""Repeatable real-model checks on downloaded videos; no cloud analysis."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from behavior_core import BehaviorConfig
from behavior_video import VideoJob


def main():
    results = []
    cases = [
        ('workshop-default', 'workshop-demo.mp4', BehaviorConfig()),
        # Deliberately configured ROI and angle threshold test the event path,
        # not a claim that this demonstrator is violating a real teaching rule.
        ('workshop-configured-events', 'workshop-demo.mp4', BehaviorConfig(roi=(0, 0, .25, 1), lean_degrees=20)),
        ('low-light-negative', 'mig-welding.webm', BehaviorConfig()),
        ('independent-college', 'college-welding.mp4', BehaviorConfig()),
    ]
    out = ROOT/'outputs/behavior-check'
    for label, name, config in cases:
        source = ROOT/'outputs/behavior-samples'/name
        job = VideoJob(source, config, out)
        job.run()
        snapshot = job.snapshot()
        assert snapshot['status'] == 'done', snapshot['error']
        report = snapshot['report']
        totals = report['totals']
        assert abs(totals['duration'] - report['video_seconds']) < .1
        assert abs(totals['inside']+totals['outside']+totals['unknown']-totals['duration']) < .01
        if label == 'workshop-default':
            assert totals['visible'] > 7 and totals['pose_observed'] > 7
            assert report['ppe_seconds']['面罩']['observed'] > 5
            assert report['ppe_seconds']['手套']['observed'] > 2
            assert report['ppe_seconds']['围裙']['observed'] > 2
            assert report['events'] == []
        elif label == 'workshop-configured-events':
            assert {'outside', 'lean'} <= {e['type'] for e in report['events']}
        elif label == 'low-light-negative':
            assert totals['visible'] == 0 and totals['unknown'] >= 36
            assert report['events'] == [] and report['inside_percent'] is None
            assert all(item['missing'] == 0 for item in report['ppe_seconds'].values())
        else:
            assert report['video_seconds'] > 120 and report['sample_count'] >= 350
            assert totals['visible'] > 30 and totals['unknown'] > 30
            assert report['ppe_seconds']['手套']['observed'] > 3
            assert report['ppe_seconds']['面罩']['observed'] > 1
        result = {'case': label, 'source': name, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'report_path': str(job.root/'report.json'), 'totals': totals,
                  'events': report['events'], 'mean_inference_ms': report['mean_inference_ms'], 'status': 'passed'}
        results.append(result)
        print(label, 'passed', f"{report['mean_inference_ms']} ms/frame", flush=True)
    (out/'model-verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
