"""系统内置连续训练记录，保存在应用唯一的识别记录数据库中。"""
from functools import lru_cache
from contextlib import closing
import io
from pathlib import Path
from PIL import Image

from scoring import DIMENSIONS, RUBRIC_VERSION, evaluate_quality
from recognition_history import connect, save_record


STAGES = (
    ('控制焊道宽度', '焊缝成形不良：前后宽窄不一', '在试板上标出参照线，练完比较三处焊道宽度。'),
    ('保持走枪速度', '焊缝成形不良：局部纹路疏密不均', '沿同一条线匀速走枪，再比较前后两段的纹路。'),
    ('改善两侧过渡', '咬边：边缘局部有凹槽', '在老师指导下调整两侧停留时间，观察边缘过渡。'),
    ('控制表面飞溅', '飞溅过多：焊道旁有颗粒', '先清理试板，在相同条件下比较焊道旁的飞溅。'),
    ('稳定焊道走向', '局部轻微跑偏', '沿标线分段练习，比较每段中心线的位置。'),
    ('巩固整体成形', '未见明显外观缺陷', '换一块试板重复练习，检查宽度和纹路能否保持一致。'),
)


@lru_cache(maxsize=1)
def demo_records():
    records = []
    for index in range(60):
        stage, offset = divmod(index, 10)
        goal, finding, suggestion = STAGES[stage]
        # Rising baseline with occasional small setbacks, shared by chart and table.
        level = 51 + 44 * index / 59 + (0, 1, 2, -1, 1, 0, -2, 1, 0, 1)[offset]
        raw = {}
        for axis, (name, maximum) in enumerate(DIMENSIONS):
            adjustment = -4 if axis == stage else (axis % 3 - 1)
            points = max(0, min(maximum, round((level + adjustment) * maximum / 100)))
            raw[name] = {'分数': points, '理由': goal + '阶段训练得分'}
        dimensions, assessment = evaluate_quality(raw, [finding])
        n = index + 1
        records.append(dict(sequence=n, run_id=f'training-record-{n:02}', generated_at='',
                            source_type='training', score=assessment['最终分'], defects=[finding],
                            reason=goal, suggestion=suggestion, rubric_version=RUBRIC_VERSION,
                            assessment=assessment, score_type=assessment['评分类型'], dimensions=dimensions,
                            photo=f'practice-{n:02}'))
    return tuple(records)


@lru_cache(maxsize=16)
def demo_photo(photo):
    return (Path(__file__).resolve().parent / 'assets' / 'growth-demo' / (photo + '.jpg')).read_bytes()


def ensure_training_records(path=None):
    """Insert the bundled progression once into the same database as live history."""
    marker = 'bundled_training_records_v1'
    with closing(connect(path)) as connection:
        row = connection.execute('SELECT value FROM recognition_metadata WHERE key=?', (marker,)).fetchone()
        if row and row['value'] == 'complete':
            return 0
        with connection:
            connection.execute('''INSERT INTO recognition_metadata(key, value) VALUES (?, 'loading')
                ON CONFLICT(key) DO UPDATE SET value='loading' ''', (marker,))

    inserted = 0
    for item in demo_records():
        with closing(connect(path)) as connection:
            exists = connection.execute('SELECT 1 FROM recognition_history WHERE run_id=?',
                                        (item['run_id'],)).fetchone()
        if exists:
            continue
        with Image.open(io.BytesIO(demo_photo(item['photo']))) as source:
            original = source.convert('RGB')
            report = {
                'run_id': item['run_id'], 'provider': '本地训练记录', 'model': '焊接外观评价',
                'learning_goal': item['reason'], 'feedback_version': 'training-record-v1',
                'focus_confidence_threshold': None, 'focus_regions': [], 'generated_at': '',
                'score': {**item['assessment'], '分数': item['assessment']['最终分'], '理由': item['reason']}, 'dimensions': item['dimensions'],
                'rubric_version': RUBRIC_VERSION, 'dimension_weights': dict(DIMENSIONS),
                'sections': {'缺陷类型': item['defects'], '图中现象': [item['defects'][0]],
                             '可能原因': [], '改良建议': [item['suggestion']]},
                'usage': {}, 'note': '',
            }
            inputs = {'source_type': 'training', 'detections': [], 'manual_observations': [],
                      'process_context': {}, 'learning_goal': item['reason'],
                      'original_size': list(original.size)}
            save_record(item['run_id'], 'training', report, path, original=original, inputs=inputs)
            inserted += 1

    with closing(connect(path)) as connection, connection:
        connection.execute('UPDATE recognition_metadata SET value=? WHERE key=?', ('complete', marker))
    return inserted
