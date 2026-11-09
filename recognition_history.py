"""Local, idempotent storage for completed teaching analyses."""
from contextlib import closing
from pathlib import Path
import json
import io
import sqlite3
from PIL import Image

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
    connection.commit()
    return connection


def save_record(run_id, source_type, report, path=None, *, annotated=None):
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
    for record in records:
        record['defects'] = json.loads(record['defects'])
    return records
