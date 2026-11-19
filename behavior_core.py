"""Observable workshop behaviour; no inference of attention or mental state.

All durations use capture/video timestamps. Missing observations never prove
absence of PPE, departure, or a normal posture. This mode follows one operator.
"""
from dataclasses import asdict, dataclass
import math

PPE_ITEMS = {
    '面罩': ({'avec_casque'}, {'sans_casque'}),
    '手套': ({'avec_gants'}, {'sans_gants'}),
    '围裙': ({'tablier_ferme'}, {'sans_tablier', 'tablier_ouvert'}),
    '鞋类': ({'chaussure_adequat'}, {'chaussure_inadequat'}),
}
EVENT_LABELS = {'outside': '工位区域外', 'lean': '躯干倾角持续偏大',
                'phone': '手部附近出现手机', **{'ppe_' + k: k + '异常线索' for k in PPE_ITEMS}}
PPE_LABELS = {'observed': '检出装备', 'missing': '异常线索',
              'uncertain': '证据不一致', 'unseen': '未观察到'}


@dataclass(frozen=True)
class BehaviorConfig:
    roi: tuple = (0.05, 0.05, 0.95, 0.95)
    lean_degrees: float = 45.0
    min_event_seconds: float = 2.0
    max_gap_seconds: float = 1.5
    ppe_threshold: float = 0.5
    keypoint_threshold: float = 0.45
    phase: str = '操作练习'

    def __post_init__(self):
        x1, y1, x2, y2 = self.roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError('工位区域范围无效')
        if not (10 <= self.lean_degrees <= 85 and self.min_event_seconds >= 0.5
                and self.max_gap_seconds > 0 and 0.25 <= self.ppe_threshold <= 0.95):
            raise ValueError('行为检测参数无效')


def torso_angle(points, threshold=0.45):
    # Shoulder -> hip pairs. A visible side suffices; do not invent hidden joints.
    sides = []
    for shoulder, hip in [(5, 11), (6, 12)]:
        a, b = points[shoulder], points[hip]
        if min(a[2], b[2]) < threshold:
            continue
        dx, dy = a[0] - b[0], b[1] - a[1]
        if math.hypot(dx, dy) < 12:
            continue
        sides.append((min(a[2], b[2]), math.degrees(math.atan2(abs(dx), dy))))
    return max(sides)[1] if sides else None


def box_iou(a, b):
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection / max(union, 1)


def ppe_evidence(detections, person, threshold):
    # The caller only supplies a single-person scene; associate evidence locally.
    x1, y1, x2, y2 = person['box']
    relevant = [d for d in detections if x1 <= (d['box'][0]+d['box'][2])/2 <= x2
                and y1 <= (d['box'][1]+d['box'][3])/2 <= y2 and d['confidence'] >= .25]
    result = {}
    for label, (worn, missing) in PPE_ITEMS.items():
        yes = [d['confidence'] for d in relevant if d['class'] in worn]
        no = [d['confidence'] for d in relevant if d['class'] in missing]
        if yes and no:
            state = 'uncertain'
        elif yes and max(yes) >= threshold:
            state = 'observed'
        elif no and max(no) >= threshold:
            state = 'missing'
        elif yes or no:
            state = 'uncertain'
        else:
            state = 'unseen'
        result[label] = state
    return result


class BehaviorAnalyzer:
    """Conservative single-person continuity plus timestamp-based event debounce."""
    def __init__(self, config=None):
        self.config = config or BehaviorConfig()
        self.start = self.last_time = None
        self.last_box = None
        self.last = None
        self.active = {}
        self.events = []
        self.samples = 0
        self.totals = dict(duration=0., visible=0., inside=0., outside=0., unknown=0.,
                           pose_observed=0., lean=0., phone=0.)
        self.ppe_seconds = {k: dict(observed=0., missing=0., uncertain=0., unseen=0.) for k in PPE_ITEMS}

    def _close(self, key):
        event = self.active.pop(key, None)
        if event and event['end'] - event['start'] >= self.config.min_event_seconds:
            self.events.append(event)

    def _interval(self, seconds, observation):
        self.totals['duration'] += seconds
        status = observation['location'] if observation else 'unknown'
        self.totals[status] += seconds
        if status != 'unknown':
            self.totals['visible'] += seconds
        if observation and observation['angle'] is not None:
            self.totals['pose_observed'] += seconds
            self.totals['lean'] += seconds * (observation['angle'] > self.config.lean_degrees)
        if observation and observation['phone']:
            self.totals['phone'] += seconds
        for name in PPE_ITEMS:
            state = observation['ppe'][name] if observation else 'unseen'
            self.ppe_seconds[name][state] += seconds

    def update(self, timestamp, people, equipment, phones, size):
        if not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError('视频时间戳无效')
        if self.last_time is not None and timestamp <= self.last_time:
            raise ValueError('视频时间戳必须递增')
        if self.start is None:
            self.start = timestamp
        dt = timestamp - self.last_time if self.last_time is not None else 0
        gap = dt > self.config.max_gap_seconds
        person = people[0] if len(people) == 1 else None
        discontinuity = bool(person and self.last_box and box_iou(person['box'], self.last_box) < .12)
        # Any disappearance, crowded scene or jump breaks continuity. Never switch
        # a tracked student to another person silently or label occlusion as leaving.
        trusted = person is not None and not discontinuity
        if gap or discontinuity:
            for key in list(self.active):
                self._close(key)
        if dt:
            self._interval(dt, self.last if not gap and not discontinuity else None)
        reason = '单人可见' if trusted else ('未检出学生' if not people else '多人或跟踪中断')
        observation = {'location': 'unknown', 'angle': None, 'phone': False,
                       'ppe': {k: 'unseen' for k in PPE_ITEMS}, 'reason': reason, 'people': len(people)}
        if trusted:
            w, h = size
            x1, y1, x2, y2 = person['box']
            cx, cy = (x1+x2)/2/w, (y1+y2)/2/h
            rx1, ry1, rx2, ry2 = self.config.roi
            observation['location'] = 'inside' if rx1 <= cx <= rx2 and ry1 <= cy <= ry2 else 'outside'
            observation['angle'] = torso_angle(person['points'], self.config.keypoint_threshold)
            observation['ppe'] = ppe_evidence(equipment, person, self.config.ppe_threshold)
            wrists = [person['points'][i] for i in (9, 10) if person['points'][i][2] >= self.config.keypoint_threshold]
            margin = max(18, (x2-x1)*.12)
            observation['phone'] = any(
                x1 <= (p['box'][0]+p['box'][2])/2 <= x2 and y1 <= (p['box'][1]+p['box'][3])/2 <= y2
                and any(p['box'][0]-margin <= wrist[0] <= p['box'][2]+margin
                        and p['box'][1]-margin <= wrist[1] <= p['box'][3]+margin for wrist in wrists)
                for p in phones if p['confidence'] >= .5)
        flags = {'outside': observation['location'] == 'outside',
                 'lean': observation['angle'] is not None and observation['angle'] > self.config.lean_degrees,
                 'phone': observation['phone'],
                 **{'ppe_'+k: v == 'missing' for k, v in observation['ppe'].items()}}
        for key, enabled in flags.items():
            if enabled:
                event = self.active.setdefault(key, {'type': key, 'label': EVENT_LABELS[key],
                                                      'start': timestamp-self.start, 'end': timestamp-self.start})
                event['end'] = timestamp-self.start
            else:
                self._close(key)
        self.last_time, self.last = timestamp, observation
        self.last_box = person['box'] if person else None
        self.samples += 1
        return self.report()

    def finish(self, timestamp=None):
        if timestamp is not None and self.last_time is not None and timestamp > self.last_time:
            dt = timestamp - self.last_time
            if dt <= self.config.max_gap_seconds:
                self._interval(dt, self.last)
                for event in self.active.values():
                    event['end'] = timestamp-self.start
            else:
                self._interval(dt, None)
            self.last_time = timestamp
        for key in list(self.active):
            self._close(key)
        return self.report()

    def report(self):
        events = self.events + [e for e in self.active.values() if e['end']-e['start'] >= self.config.min_event_seconds]
        events = [dict(e, start=round(e['start'], 2), end=round(e['end'], 2),
                       seconds=round(e['end']-e['start'], 2)) for e in events]
        duration, visible = self.totals['duration'], self.totals['visible']
        tips = []
        if self.totals['unknown'] > duration*.3 or not visible:
            tips.append('部分时段无法观察到单个学生，不计为离岗或违规。')
        if any(e['type'] == 'outside' for e in events):
            tips.append('存在工位区域外片段，请结合取料、清理或教师指导安排理解。')
        if any(e['type'] == 'lean' for e in events):
            tips.append('存在持续倾斜片段，可调整工件高度与站位，减少长时间维持同一姿势。')
        if any(e['type'].startswith('ppe_') for e in events):
            tips.append('发现防护用品异常线索，施焊前按面罩、手套、围裙、鞋类逐项检查。')
        if any(e['type'] == 'phone' for e in events):
            tips.append('有手部附近出现手机的片段，操作工具时将手机放置到安全位置。')
        if not tips:
            tips.append('当前未记录持续异常事件，继续按实训流程完成操作。')
        return {'schema_version': 1, 'mode': 'observable_behavior', 'config': asdict(self.config),
                'totals': {k: round(v, 3) for k, v in self.totals.items()},
                'coverage_percent': round(100*visible/duration, 1) if duration else None,
                'inside_percent': round(100*self.totals['inside']/visible, 1) if visible else None,
                'ppe_seconds': {k: {s: round(v, 3) for s, v in values.items()} for k, values in self.ppe_seconds.items()},
                'latest': self.last, 'events': sorted(events, key=lambda x: x['start']),
                'samples': self.samples, 'suggestions': tips,
                'scope': '单工位可观察行为；不是心理专注度、技能成绩或安全认证。面罩检出不等同于面屏已放下。'}
