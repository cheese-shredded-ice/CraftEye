"""Local, idempotent storage for completed teaching analyses."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3

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
    connection.commit()
    return connection


def save_record(run_id, source_type, report, path=None):
    score = report['score']['分数']
    if score is not None and (type(score) is not int or not 0 <= score <= 100):
        raise ValueError('Invalid score')
    with closing(connect(path)) as connection, connection:
        connection.execute('''INSERT INTO recognition_history
            (run_id, generated_at, source_type, score, defects, reason, suggestion)
            VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(run_id) DO NOTHING''',
            (run_id, report['generated_at'], source_type, score,
             json.dumps(report['sections']['缺陷类型'], ensure_ascii=False),
             report['score']['理由'], '\n'.join(report['sections']['改良建议'])))


def load_records(path=None):
    with closing(connect(path)) as connection:
        records = [dict(row) for row in connection.execute('SELECT * FROM recognition_history ORDER BY sequence')]
    for record in records:
        record['defects'] = json.loads(record['defects'])
    return records
