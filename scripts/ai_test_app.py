"""Isolated UI test app: replaces HTTP transport; never calls the cloud API."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ai_analysis
import ai_ui
import recognition_history
import streamlit as st

recognition_history.HISTORY_DB = ROOT / 'outputs/ai-check/history-test.sqlite3'


class Reply:
    def __init__(self, body, status=200):
        self.status_code, self.body = status, body

    def json(self):
        return self.body

    def close(self):
        pass


def simulated_post(url, **kwargs):
    assert kwargs['headers']['Authorization'] == 'Bearer test-key-not-real'
    content = kwargs['json']['messages'][0]['content']
    images = [item['image_url']['url'] for item in content if item['type'] == 'image_url']
    assert 2 <= len(images) <= 10
    assert all(item.startswith('data:image/jpeg;base64,') for item in images)
    record = {'images': len(images), 'focus_crops': len(images) - 2, 'distinct_images': images[0] != images[1],
              'model': kwargs['json']['model'], 'simulated': True}
    with (ROOT / 'outputs/ai-check/requests.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(record) + '\n')
    time.sleep(0.8)
    if kwargs['json']['model'] == 'simulate-401':
        return Reply({'error': 'test-key-not-real must not be displayed'}, status=401)
    sections = {'本次评分': {'分数': 76, '理由': '模拟：焊道较连续，边缘过渡需练习。'},
                '缺陷类型': ['疑似气孔：模拟，表面可见小孔。', '疑似咬边：模拟，边缘有凹槽。'],
                '图中现象': ['模拟：焊道连续，局部宽窄不一致。'],
                '可能原因': ['模拟：走枪速度可能不稳定，需观察操作确认。'],
                '改良建议': ['模拟：下次匀速走枪，比较前中后段宽度。']}
    return Reply({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(sections)}}],
                  'usage': {'total_tokens': 100}})


def simulated_analysis(*args, **kwargs):
    return ai_analysis.analyze(*args, transport=simulated_post, **kwargs)


ai_ui.analyze = simulated_analysis
ai_ui.local_api_key = lambda: ''
os.environ.pop('DASHSCOPE_API_KEY', None)
exec(compile((ROOT / 'app.py').read_text(encoding='utf-8'), str(ROOT / 'app.py'), 'exec'))
st.html('<style>[data-testid="stElementContainer"]:has([data-test-ready]){display:none}</style>'
        '<span data-test-ready="true" style="display:none"></span>')
