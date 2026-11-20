"""Local, idempotent storage for completed teaching analyses."""
from contextlib import closing
from pathlib import Path
import json
import io
import sqlite3
from PIL import Image
from .common import ROOT
from .scoring import RUBRIC_VERSION

HISTORY_DB = ROOT / 'outputs' / 'recognition-history.sqlite3'

# Number all surviving records before filtering or pagination. Keep the stored
# primary key unchanged so deletion and saved report identities remain stable.
ORDERED_HISTORY = '''SELECT *, ROW_NUMBER() OVER (ORDER BY sequence) AS display_sequence
                     FROM recognition_history'''


def connect(path=None):
    path = Path(path or HISTORY_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_history (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        generated_at TEXT NOT NULL,
        source_type TEXT NOT NULL,
        score INTEGER CHECK(score BETWEEN 0 AND 100),
        defects TEXT NOT NULL,
        reason TEXT NOT NULL,
        suggestion TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_images (
        run_id TEXT PRIMARY KEY,
        annotated_png BLOB NOT NULL,
        thumbnail_png BLOB NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_originals (
        run_id TEXT PRIMARY KEY,
        original_png BLOB NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_scoring (
        run_id TEXT PRIMARY KEY,
        rubric_version TEXT NOT NULL,
        dimensions TEXT NOT NULL,
        weights TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_assessment (
        run_id TEXT PRIMARY KEY,
        score_json TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_reports (
        run_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        report_json TEXT NOT NULL,
        inputs_json TEXT NOT NULL
    )''')
    connection.execute('''CREATE TABLE IF NOT EXISTS recognition_metadata (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')
    connection.commit()
    return connection


REPORT_FIELDS = {'run_id', 'provider', 'model', 'learning_goal', 'feedback_version',
                 'focus_confidence_threshold', 'focus_regions', 'generated_at', 'score',
                 'dimensions', 'rubric_version', 'dimension_weights', 'sections', 'usage', 'note', 'audit'}
INPUT_FIELDS = {'source_id', 'source_type', 'detections', 'manual_observations',
                'process_context', 'learning_goal', 'original_size'}


def save_record(run_id, source_type, report, path=None, *, annotated=None, original=None, inputs=None):
    score = report['score']['分数']
    if score is not None and (type(score) is not int or not 0 <= score <= 100):
        raise ValueError('Invalid score')
    image_data = None
    if annotated is not None:
        original_buffer, thumb_buffer = io.BytesIO(), io.BytesIO()
        annotated.save(original_buffer, format='PNG')
        thumbnail = annotated.convert('RGB').copy()
        thumbnail.thumbnail((400, 240), Image.Resampling.LANCZOS)
        thumbnail.save(thumb_buffer, format='PNG')
        image_data = (original_buffer.getvalue(), thumb_buffer.getvalue())
    with closing(connect(path)) as connection, connection:
        cursor = connection.execute('''INSERT INTO recognition_history
            (run_id, generated_at, source_type, score, defects, reason, suggestion)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING''',
            (run_id, report['generated_at'], source_type, score,
             json.dumps(report['sections']['缺陷类型'], ensure_ascii=False),
             report['score']['理由'], '\n'.join(report['sections']['改良建议'])))
        if cursor.rowcount and image_data:
            connection.execute('INSERT INTO recognition_images VALUES (?, ?, ?)', (run_id, *image_data))
        if cursor.rowcount and original is not None:
            buffer = io.BytesIO()
            original.convert('RGB').save(buffer, format='PNG')
            connection.execute('INSERT INTO recognition_originals VALUES (?, ?)', (run_id, buffer.getvalue()))
        if cursor.rowcount and report.get('dimensions'):
            connection.execute('INSERT INTO recognition_scoring VALUES (?, ?, ?, ?)',
                (run_id, report['rubric_version'], json.dumps(report['dimensions'], ensure_ascii=False),
                 json.dumps(report['dimension_weights'], ensure_ascii=False)))
        if cursor.rowcount and report['score'].get('评分版本'):
            connection.execute('INSERT INTO recognition_assessment VALUES (?, ?)',
                               (run_id, json.dumps(report['score'], ensure_ascii=False)))
        if cursor.rowcount:
            # Persist the complete result, not configuration/credentials or a
            # later recomputation under a different scoring or prompt version.
            stored_report = {key: value for key, value in report.items() if key in REPORT_FIELDS}
            stored_inputs = {key: value for key, value in (inputs or {}).items() if key in INPUT_FIELDS}
            stored_inputs['source_type'] = source_type
            connection.execute('INSERT INTO recognition_reports VALUES (?, ?, ?, ?)',
                (run_id, 1, json.dumps(stored_report, ensure_ascii=False), json.dumps(stored_inputs, ensure_ascii=False)))


def load_picker_records(path=None):
    """The image picker is original-only; never pass an old overlay back to YOLO."""
    with closing(connect(path)) as connection:
        return [dict(row) for row in connection.execute(f'''
            SELECT h.run_id, h.sequence, h.display_sequence, h.generated_at, h.defects,
                   (o.run_id IS NOT NULL) AS has_original
            FROM ({ORDERED_HISTORY}) h
            JOIN recognition_originals o ON o.run_id=h.run_id
            WHERE h.source_type != 'training'
            ORDER BY h.sequence DESC LIMIT 50''')]


def load_picker_image(run_id, path=None):
    with closing(connect(path)) as connection:
        row = connection.execute('''SELECT o.original_png AS image
            FROM recognition_history h
            JOIN recognition_originals o ON o.run_id=h.run_id
            WHERE h.run_id=? AND h.source_type != 'training' ''', (run_id,)).fetchone()
        return row['image'] if row else None


def load_original_images(run_ids, path=None):
    """Small previews of genuine originals; absent originals remain absent."""
    if not run_ids:
        return {}
    with closing(connect(path)) as connection:
        rows = connection.execute(f'SELECT run_id, original_png FROM recognition_originals WHERE run_id IN ({",".join("?" for _ in run_ids)})', list(run_ids))
        images = {}
        for row in rows:
            with Image.open(io.BytesIO(row['original_png'])) as image:
                thumbnail = image.convert('RGB')
                thumbnail.thumbnail((400, 240), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                thumbnail.save(buffer, format='PNG')
                images[row['run_id']] = buffer.getvalue()
        return images


def load_record_detail(run_id, path=None):
    with closing(connect(path)) as connection:
        record = connection.execute(f'SELECT * FROM ({ORDERED_HISTORY}) WHERE run_id=?', (run_id,)).fetchone()
        if record is None:
            return None
        saved = connection.execute('SELECT * FROM recognition_reports WHERE run_id=?', (run_id,)).fetchone()
        original = connection.execute('SELECT original_png FROM recognition_originals WHERE run_id=?', (run_id,)).fetchone()
        annotated = connection.execute('SELECT annotated_png FROM recognition_images WHERE run_id=?', (run_id,)).fetchone()
        scoring = connection.execute('SELECT * FROM recognition_scoring WHERE run_id=?', (run_id,)).fetchone()
        assessment = connection.execute('SELECT score_json FROM recognition_assessment WHERE run_id=?', (run_id,)).fetchone()
    if saved:
        report, inputs = json.loads(saved['report_json']), json.loads(saved['inputs_json'])
    else:
        # Recover only fields actually stored by older releases. Missing narrative
        # and inputs cannot be recreated without inventing a historical result.
        report = {'generated_at': record['generated_at'],
                  'score': json.loads(assessment[0]) if assessment else {'分数': record['score'], '理由': record['reason']},
                  'sections': {'缺陷类型': json.loads(record['defects']), '改良建议': record['suggestion'].splitlines()}}
        if scoring:
            report.update(dimensions=json.loads(scoring['dimensions']),
                          dimension_weights=json.loads(scoring['weights']), rubric_version=scoring['rubric_version'])
        inputs = {'source_type': record['source_type']}
    return {'run_id': run_id, 'sequence': record['sequence'], 'display_sequence': record['display_sequence'], 'analysis': report, 'inputs': inputs,
            'complete_snapshot': bool(saved), 'schema_version': saved['schema_version'] if saved else 0,
            'original_png': original[0] if original else None, 'annotated_png': annotated[0] if annotated else None}


def load_record_images(run_ids, path=None, *, full_size=False):
    if not run_ids:
        return {}
    column = 'annotated_png' if full_size else 'thumbnail_png'
    with closing(connect(path)) as connection:
        rows = connection.execute(f'SELECT run_id, {column} FROM recognition_images WHERE run_id IN ({",".join("?" for _ in run_ids)})', list(run_ids))
        return {row[0]: row[1] for row in rows}


def load_records(path=None):
    with closing(connect(path)) as connection:
        records = [dict(row) for row in connection.execute(f'{ORDERED_HISTORY} ORDER BY sequence')]
        scoring = {row['run_id']: dict(row) for row in connection.execute('SELECT * FROM recognition_scoring')}
        assessments = {row['run_id']: json.loads(row['score_json'])
                       for row in connection.execute('SELECT * FROM recognition_assessment')}
    for record in records:
        record['defects'] = json.loads(record['defects'])
        detail = scoring.get(record['run_id'])
        record['dimensions'] = json.loads(detail['dimensions']) if detail else None
        record['rubric_version'] = detail['rubric_version'] if detail else None
        record['dimension_weights'] = json.loads(detail['weights']) if detail else None
        record['score_type'] = None
        record['assessment'] = assessments.get(record['run_id'])
        if record['assessment']:
            record['score_type'] = record['assessment']['评分类型']
        elif detail and detail['rubric_version'] in (RUBRIC_VERSION, 'welding-v4-path-points-v4', 'welding-v4-image-points-v3'):
            record['score_type'] = '无法评分' if record['score'] is None else '外观参考分'
        elif detail and detail['rubric_version'] == 'welding-v4-raw-points-v2':
            record['score_type'] = ('无法评分' if record['score'] is None else
                '外观参考分' if record['dimensions']['接头强度']['得分'] is None else '完整综合分')
    return records


def delete_records(run_ids, path=None):
    """Delete explicitly selected records and their images in one transaction."""
    selected = tuple(dict.fromkeys(run_ids))
    if not selected:
        return 0
    if any(not isinstance(run_id, str) or not run_id for run_id in selected):
        raise ValueError('Invalid record identifiers')
    with closing(connect(path)) as connection, connection:
        removed = 0
        for run_id in selected:
            connection.execute('DELETE FROM recognition_images WHERE run_id = ?', (run_id,))
            connection.execute('DELETE FROM recognition_originals WHERE run_id = ?', (run_id,))
            connection.execute('DELETE FROM recognition_scoring WHERE run_id = ?', (run_id,))
            connection.execute('DELETE FROM recognition_assessment WHERE run_id = ?', (run_id,))
            connection.execute('DELETE FROM recognition_reports WHERE run_id = ?', (run_id,))
            removed += connection.execute('DELETE FROM recognition_history WHERE run_id = ?', (run_id,)).rowcount
    return removed
