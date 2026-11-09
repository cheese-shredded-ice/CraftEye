"""Isolated UI test app: replaces HTTP transport; never calls the cloud API."""
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ai_analysis
import ai_ui
import streamlit as st


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
    assert len(images) == 2
    assert all(item.startswith('data:image/jpeg;base64,') for item in images)
    record = {'images': len(images), 'distinct_images': images[0] != images[1],
              'model': kwargs['json']['model'], 'simulated': True}
    with (ROOT / 'outputs/ai-check/requests.jsonl').open('a', encoding='utf-8') as output:
        output.write(json.dumps(record) + '\n')
    time.sleep(0.8)
    if '模拟401' in content[0]['text']:
        return Reply({'error': 'test-key-not-real must not be displayed'}, status=401)
    sections = {'图中现象': ['模拟测试：图中焊缝存在成形不均匀的区域。'],
                '可能原因': ['模拟测试：行走速度可能不稳定，需现场核实。'],
                '改良建议': ['模拟测试：先核对工艺规程，再保持行走速度稳定并试焊复检。']}
    return Reply({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(sections)}}],
                  'usage': {'total_tokens': 100}})


def simulated_analysis(*args, **kwargs):
    return ai_analysis.analyze(*args, transport=simulated_post, **kwargs)


ai_ui.analyze = simulated_analysis
exec(compile((ROOT / 'app.py').read_text(encoding='utf-8'), str(ROOT / 'app.py'), 'exec'))
st.caption('当前端口仅供模拟 AI 接口测试，不会向通义千问发送请求。')
