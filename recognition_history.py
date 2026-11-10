"""Local, idempotent storage for completed teaching analyses."""
from contextlib import closing
from pathlib import Path
import json
import io
import sqlite3
from PIL import Image
from scoring import RUBRIC_VERSION

HISTORY_DB = Path(__file__).resolve().parent / 'outputs' / 'recognition-history.sqlite3'


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
    connection.commit()
    return connection


def save_record(run_id, source_type, report, path=None, *, annotated=None, original=None):
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


def load_picker_records(path=None):
    """List only records with images, without loading image blobs or full reports."""
    with closing(connect(path)) as connection:
        return [dict(row) for row in connection.execute('''
            SELECT h.run_id, h.sequence, h.generated_at, h.defects,
                   (o.run_id IS NOT NULL) AS has_original
            FROM recognition_history h
            JOIN recognition_images i ON i.run_id=h.run_id
            LEFT JOIN recognition_originals o ON o.run_id=h.run_id
            ORDER BY h.sequence DESC LIMIT 50''')]


def load_picker_image(run_id, path=None):
    with closing(connect(path)) as connection:
        row = connection.execute('''SELECT COALESCE(o.original_png,i.annotated_png) AS image
            FROM recognition_history h
            JOIN recognition_images i ON i.run_id=h.run_id
            LEFT JOIN recognition_originals o ON o.run_id=h.run_id
            WHERE h.run_id=?''', (run_id,)).fetchone()
        return row['image'] if row else None


def load_record_images(run_ids, path=None, *, full_size=False):
    if not run_ids:
        return {}
    column = 'annotated_png' if full_size else 'thumbnail_png'
    with closing(connect(path)) as connection:
        rows = connection.execute(f'SELECT run_id, {column} FROM recognition_images WHERE run_id IN ({",".join("?" for _ in run_ids)})', list(run_ids))
        return {row[0]: row[1] for row in rows}


def load_records(path=None):
    with closing(connect(path)) as connection:
        records = [dict(row) for row in connection.execute('SELECT * FROM recognition_history ORDER BY sequence')]
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
            removed += connection.execute('DELETE FROM recognition_history WHERE run_id = ?', (run_id,)).rowcount
    return removed
