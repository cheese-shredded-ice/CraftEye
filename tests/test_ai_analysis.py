import base64
import io
import json
import unittest

from PIL import Image
import requests

from ai_analysis import (AIConfig, AnalysisError, SECTIONS, analyze, analysis_identity,
                         endpoint_url, parse_analysis, report_text)


class Reply:
    def __init__(self, body=None, status=200):
        self.status_code, self.body = status, body
        self.closed = False

    def json(self):
        return self.body

    def close(self):
        self.closed = True


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        self.original = Image.new('RGB', (200, 100), 'gray')
        self.annotated = Image.new('RGB', (200, 100), 'red')
        self.rows = [{'类别': '焊接不良', '置信度': 0.8}]
        self.config = AIConfig('test-secret-not-real')
        self.sections = {'图中现象': ['局部成形不均匀。'], '可能原因': ['行走速度可能不均，需要核实。'],
                         '改良建议': ['先核对工艺规程，保持行走稳定并试焊复检。']}

    def test_request_contains_both_images_and_context_and_secret_not_exported(self):
        calls = []
        reply = Reply({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(self.sections)}}],
                       'usage': {'total_tokens': 123}})

        def post(url, **kwargs):
            calls.append((url, kwargs))
            return reply

        result = analyze(self.original, self.annotated, self.rows, ['成形不均匀'], '板厚3mm', self.config, transport=post)
        self.assertEqual(len(calls), 1)
        url, request = calls[0]
        self.assertTrue(url.endswith('/chat/completions'))
        self.assertFalse(request['allow_redirects'])
        content = request['json']['messages'][0]['content']
        images = [item['image_url']['url'] for item in content if item['type'] == 'image_url']
        self.assertEqual(len(images), 2)
        self.assertNotEqual(images[0], images[1])
        self.assertEqual(Image.open(io.BytesIO(base64.b64decode(images[0].split(',')[1]))).size, (200, 100))
        self.assertIn('板厚3mm', content[0]['text'])
        self.assertIn('焊接不良', content[0]['text'])
        self.assertNotIn(self.config.api_key, json.dumps(result))
        self.assertNotIn(self.config.api_key, repr(self.config))
        self.assertTrue(reply.closed)
        for title in SECTIONS:
            self.assertIn('【' + title + '】', report_text(result))

    def test_error_does_not_expose_provider_body_and_no_automatic_retry(self):
        calls = []
        reply = Reply({'message': self.config.api_key}, status=401)

        def post(*args, **kwargs):
            calls.append(1)
            return reply

        with self.assertRaises(AnalysisError) as error:
            analyze(self.original, self.annotated, self.rows, [], '', self.config, transport=post)
        self.assertIn('验证失败', str(error.exception))
        self.assertNotIn(self.config.api_key, str(error.exception))
        self.assertEqual(len(calls), 1)
        self.assertTrue(reply.closed)

    def test_timeout_is_safe(self):
        def post(*args, **kwargs):
            raise requests.Timeout(self.config.api_key)
        with self.assertRaises(AnalysisError) as error:
            analyze(self.original, self.annotated, [], [], '', self.config, transport=post)
        self.assertIn('超时', str(error.exception))
        self.assertNotIn(self.config.api_key, str(error.exception))

    def test_input_changes_invalidate_report_without_using_key_as_identity(self):
        def identity(image=self.original, rows=self.rows, observations=(), context='', config=self.config):
            return analysis_identity(image, self.annotated, rows, observations, context, config)
        original = identity()
        self.assertNotEqual(original, identity(image=Image.new('RGB', (200, 100), 'white')))
        self.assertNotEqual(original, identity(context='电流120A'))
        self.assertNotEqual(original, identity(observations=['飞溅']))
        self.assertNotEqual(original, identity(rows=[]))
        self.assertNotEqual(original, identity(config=AIConfig('test', model='qwen3-vl-flash')))
        self.assertEqual(original, identity(config=AIConfig('different-secret')))

    def test_invalid_or_incomplete_ai_output_is_not_faked(self):
        for value in ('不是JSON', '{}', '{"图中现象":[]}', json.dumps({**self.sections, 'extra': 'bad'})):
            with self.assertRaises(AnalysisError):
                parse_analysis(value)
        self.assertEqual(parse_analysis('```json\n' + json.dumps(self.sections) + '\n```'), self.sections)
        reply = Reply({'choices': [{'finish_reason': 'length', 'message': {'content': json.dumps(self.sections)}}]})
        with self.assertRaisesRegex(AnalysisError, '截断'):
            analyze(self.original, self.annotated, [], [], '', self.config, transport=lambda *a, **k: reply)

    def test_only_expected_alibaba_endpoints_accept_credentials(self):
        for url in ('http://dashscope.aliyuncs.com/compatible-mode/v1',
                    'https://dashscope.aliyuncs.com.evil.example/compatible-mode/v1',
                    'https://user:password@dashscope.aliyuncs.com/compatible-mode/v1',
                    'https://dashscope.aliyuncs.com/compatible-mode/v1?key=bad'):
            with self.assertRaises(AnalysisError):
                endpoint_url(url)
        self.assertEqual(endpoint_url('https://space.cn-beijing.maas.aliyuncs.com/compatible-mode/v1'),
                         'https://space.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions')


if __name__ == '__main__':
    unittest.main()
