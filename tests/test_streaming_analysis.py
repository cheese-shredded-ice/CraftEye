import json
import base64
import re
import unittest
import requests

from PIL import Image

from ai_analysis import AIConfig, AnalysisError, analyze, _stream_content, endpoint_url
from ai_ui import partial_report
from scoring import DIMENSIONS
from analysis_audit import analysis_status_lines
from teaching_report_ui import dimensions_html, report_html


class StreamReply:
    status_code = 200

    def __init__(self, content):
        self.content = content
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        for event in self.content:
            yield 'data: ' + json.dumps({'choices': [{'delta': {'content': event}}]}, ensure_ascii=False)
        yield 'data: [DONE]'

    def close(self):
        self.closed = True


class StreamingAnalysisTest(unittest.TestCase):
    def test_utf8_is_decoded_without_requests_charset_guess(self):
        response = requests.Response()
        response.encoding = 'ISO-8859-1'
        body = {'六维评分': {}, '文字': '焊道连续'}
        event = json.dumps({'choices': [{'delta': {'content': json.dumps(body, ensure_ascii=False)}}]}, ensure_ascii=False)
        response._content = ('data: ' + event + '\n\ndata: [DONE]\n').encode('utf-8')
        response._content_consumed = True
        self.assertEqual(_stream_content(response, lambda *_: None), body)

    def test_limit_applies_to_entire_stream_not_just_current_line(self):
        response = StreamReply(['{}\n' * 1000] * 15)
        with self.assertRaisesRegex(AnalysisError, '内容过长'):
            _stream_content(response, lambda *_: None)

    def test_truncated_stream_is_rejected_even_after_report_event(self):
        class TruncatedReply:
            def iter_lines(self, **kwargs):
                yield 'data: ' + json.dumps({'choices': [{'finish_reason': 'length', 'delta': {}}]})
        with self.assertRaisesRegex(AnalysisError, '截断'):
            _stream_content(TruncatedReply(), lambda *_: None)

    def test_network_failure_after_headers_is_safe_and_response_closed(self):
        class BrokenReply(StreamReply):
            def iter_lines(self, **kwargs):
                yield b'data: {}'
                raise requests.ConnectionError('secret credentials')
        response = BrokenReply([])
        with self.assertRaisesRegex(AnalysisError, '连接中断') as error:
            analyze(Image.new('RGB', (20,20)), Image.new('RGB', (20,20)), [], [], '',
                    AIConfig('secret'), transport=lambda *a, **kw: response, on_dimension=lambda *_: None)
        self.assertNotIn('secret', str(error.exception))
        self.assertTrue(response.closed)

    def test_malformed_endpoint_is_actionable_error(self):
        for url in ('https://dashscope.aliyuncs.com:bad/compatible-mode/v1', 'https://[broken'):
            with self.subTest(url=url), self.assertRaisesRegex(AnalysisError, '接口地址格式'):
                endpoint_url(url)

    def test_partial_snapshot_updates_only_received_dimensions(self):
        first_name, first_max = DIMENSIONS[0]
        snapshot = partial_report({first_name: {'分数': first_max, '理由': '焊道宽窄均匀'}}, '基础成形')
        self.assertEqual(snapshot['dimensions'][first_name]['分数'], 100)
        self.assertIsNone(snapshot['dimensions'][DIMENSIONS[1][0]]['分数'])
        self.assertEqual(snapshot['dimensions'][DIMENSIONS[1][0]]['理由'], '等待识别')
        self.assertEqual(snapshot['score']['等级'], '分析中')
        self.assertEqual(snapshot['score']['是否达到教学目标'], '分析中')
        self.assertEqual(snapshot['score']['分数'], first_max)
        rendered = report_html(snapshot, Image.new('RGB', (20, 20)), '六维评分')
        self.assertIn(f'data-weld-score="{first_max}"', rendered)
        self.assertIn('焊道宽窄均匀', rendered)
        self.assertIn('1/6', ' '.join(analysis_status_lines(snapshot)))
        radar = dimensions_html(snapshot['dimensions'])
        svg_data = re.search(r'src="data:image/svg\+xml;base64,([^"]+)"', radar).group(1)
        self.assertIn('20/20分', base64.b64decode(svg_data).decode('utf-8'))

    def test_partial_score_accumulates_raw_weighted_points_from_zero(self):
        first_name, first_max = DIMENSIONS[0]
        second_name, second_max = DIMENSIONS[1]
        snapshot = partial_report({
            first_name: {'分数': first_max // 2, '理由': '焊道宽窄基本均匀'},
            second_name: {'分数': second_max, '理由': '焊道连续'},
        }, '基础成形')
        # Dimension maxima add up to 100, so the raw rubric points are already
        # the meaningful 0–100 progress value; do not normalize by visible axes.
        self.assertEqual(snapshot['score']['分数'], first_max // 2 + second_max)

    def test_dimensions_are_published_before_final_report(self):
        dimensions = {name: {'分数': maximum, '理由': '图像可见表现良好'} for name, maximum in DIMENSIONS}
        final = {'本次评分': {'理由': '整体表现稳定'}, '六维评分': dimensions,
                 '缺陷类型': ['未见明显外观缺陷'], '图中现象': ['焊道连续'],
                 '可能原因': ['训练动作较稳定'], '改良建议': ['保持匀速练习']}
        events = [json.dumps({'type': 'dimension', 'name': name, 'score': maximum,
                              'reason': '图像可见表现良好'}, ensure_ascii=False) + '\n'
                  for name, maximum in DIMENSIONS]
        events.append(json.dumps({'type': 'report', 'result': final}, ensure_ascii=False) + '\n')
        received = []

        def post(url, **kwargs):
            self.assertTrue(kwargs['stream'])
            self.assertTrue(kwargs['json']['stream'])
            return StreamReply(events)

        report = analyze(Image.new('RGB', (20, 20)), Image.new('RGB', (20, 20)), [], [], '',
                         AIConfig('secret'), transport=post,
                         on_dimension=lambda name, item: received.append((name, item)))
        self.assertEqual([name for name, _ in received], [name for name, _ in DIMENSIONS])
        self.assertEqual(report['score']['分数'], 100)
        rendered = report_html(report, Image.new('RGB', (20, 20)), '六维评分')
        self.assertEqual(rendered.count('class="analysis-status-only"'), 1)
        self.assertIn('analysis-status-light is-complete', rendered)
        self.assertNotIn('<details class="analysis-audit"', rendered)

    def test_unterminated_final_dimension_is_published_once(self):
        name, maximum = DIMENSIONS[0]
        event = json.dumps({'type': 'dimension', 'name': name, 'score': maximum,
                            'reason': '焊道宽度均匀'}, ensure_ascii=False)
        dimensions = {axis: {'分数': points, '理由': '图像可见表现良好'} for axis, points in DIMENSIONS}
        final = {'本次评分': {'理由': '整体表现稳定'}, '六维评分': dimensions,
                 '缺陷类型': ['未见明显外观缺陷'], '图中现象': ['焊道连续'],
                 '可能原因': ['训练动作较稳定'], '改良建议': ['保持匀速练习']}
        report_event = json.dumps({'type': 'report', 'result': final}, ensure_ascii=False) + '\n'
        received = []
        # The final dimension arrives as an unterminated NDJSON tail after the
        # report event; it must still be published once and not replayed from
        # the final report's complete dimensions.
        response = StreamReply([report_event, event])
        report = analyze(Image.new('RGB', (20, 20)), Image.new('RGB', (20, 20)), [], [], '',
                         AIConfig('secret'), transport=lambda *a, **kw: response,
                         on_dimension=lambda axis, item: received.append((axis, item)))
        self.assertEqual([axis for axis, _ in received].count(name), 1)
        self.assertEqual(set(axis for axis, _ in received), {axis for axis, _ in DIMENSIONS})
        self.assertEqual(received[0][1], {'分数': maximum, '理由': '焊道宽度均匀'})
        self.assertEqual(report['score']['分数'], 100)

    def test_streaming_does_not_expose_reasoning_or_key(self):
        final = {'本次评分': {'理由': '整体表现稳定'},
                 '六维评分': {name: {'分数': maximum, '理由': '表现良好'} for name, maximum in DIMENSIONS},
                 '缺陷类型': ['未见明显外观缺陷'], '图中现象': ['焊道连续'],
                 '可能原因': ['动作稳定'], '改良建议': ['保持匀速']}
        events = [json.dumps({'type': 'internal_reasoning', 'text': 'hidden'}, ensure_ascii=False) + '\n',
                 json.dumps({'type': 'report', 'result': final}, ensure_ascii=False) + '\n']
        report = analyze(Image.new('RGB', (20, 20)), Image.new('RGB', (20, 20)), [], [], '',
                         AIConfig('secret'), transport=lambda *a, **kw: StreamReply(events), on_dimension=lambda *_: None)
        self.assertNotIn('hidden', json.dumps(report, ensure_ascii=False))
        self.assertNotIn('secret', json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    unittest.main()
