"""DashScope visual analysis. Requests happen only on an explicit user action."""
import base64
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from PIL import Image, ImageOps
import requests
from scoring import (DIMENSIONS, RUBRIC_VERSION, evaluate_quality, SCORE_FORMULA,
                     PASS_SCORE, PASS_MINIMUM, EXCELLENT_SCORE, EXCELLENT_MINIMUM)
from focus_regions import FOCUS_CONFIDENCE, MAX_FOCUS_CROPS, focus_regions
from analysis_audit import build_audit

DEFAULT_ENDPOINT = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
DEFAULT_MODEL = 'qwen3-vl-plus'
SECTIONS = ('缺陷类型', '图中现象', '可能原因', '改良建议')
DEFAULT_LEARNING_GOAL = '基础成形：焊道连续、宽窄基本一致'
FEEDBACK_VERSION = 'student-v9-critical-cap-v16'
DEFECT_TYPES = ('气孔', '夹渣', '裂纹', '未焊透', '未熔合', '咬边', '焊瘤', '烧穿', '弧坑',
                '飞溅过多', '焊缝成形不良')


class AnalysisError(Exception):
    """Safe, user-facing error; never include API headers or raw provider errors."""


@dataclass(frozen=True)
class AIConfig:
    api_key: str = field(repr=False)
    endpoint: str = DEFAULT_ENDPOINT
    model: str = DEFAULT_MODEL


def endpoint_url(value):
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or '').lower()
        port = parsed.port
    except (ValueError, AttributeError):
        raise AnalysisError('接口地址格式无效，请从百炼控制台复制完整地址。') from None
    allowed = host in {'dashscope.aliyuncs.com', 'dashscope-intl.aliyuncs.com', 'dashscope-us.aliyuncs.com'}
    allowed = allowed or (host.endswith('.maas.aliyuncs.com') and '{' not in host and '}' not in host)
    if (parsed.scheme != 'https' or not allowed or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port not in (None, 443)):
        raise AnalysisError('请填写百炼控制台提供的 HTTPS 接口地址，支持 DashScope 或工作空间专属 maas.aliyuncs.com 地址。')
    path = parsed.path.rstrip('/')
    if path.endswith('/chat/completions'):
        path = path[:-len('/chat/completions')]
    if path != '/compatible-mode/v1':
        raise AnalysisError('接口地址应以 /compatible-mode/v1 结尾；可从百炼控制台复制。')
    return urlunsplit(('https', parsed.netloc, path + '/chat/completions', '', ''))


def image_bytes(image):
    normalized = ImageOps.exif_transpose(image).convert('RGB')
    normalized.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    normalized.save(output, format='JPEG', quality=90)
    return output.getvalue()


def analysis_identity(original, annotated, rows, observations, context, config, learning_goal=DEFAULT_LEARNING_GOAL):
    digest = hashlib.sha256()
    digest.update(image_bytes(original))
    digest.update(image_bytes(annotated))
    digest.update(json.dumps({'detections': rows, 'manual_observations': list(observations),
        'process_context': context.strip(), 'learning_goal': learning_goal.strip() or DEFAULT_LEARNING_GOAL,
        'feedback_version': FEEDBACK_VERSION, 'model': config.model.strip(),
        'endpoint': config.endpoint.strip().rstrip('/')}, sort_keys=True, ensure_ascii=False).encode())
    return digest.hexdigest()


STREAM_INSTRUCTIONS = '''\n\n流式输出协议：请只输出NDJSON，每行一个JSON对象，不要Markdown。先按固定顺序逐项输出六行维度事件：{"type":"dimension","name":"成形质量","score":18,"reason":"焊道宽度均匀"}。name必须是六维名称之一，score为该项原始分整数或null。六个维度全部输出后，最后输出一行 {"type":"report","result":完整的最终JSON对象}。最终JSON必须遵守上文格式且与已发维度完全一致。只输出这些教学评价结果，不输出分析思维过程。'''


def make_payload(original, annotated, rows, observations, context, model, learning_goal=DEFAULT_LEARNING_GOAL,
                 *, stream=False):
    context = context.strip()
    if len(context) > 2000:
        raise AnalysisError('补充工艺信息请控制在 2000 字以内。')
    learning_goal = learning_goal.strip() or DEFAULT_LEARNING_GOAL
    if len(learning_goal) > 200:
        raise AnalysisError('本次训练目标请控制在 200 字以内。')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', model):
        raise AnalysisError('请填写有效的视觉模型名称。')
    regions = focus_regions(rows, original.size)
    prompt = Path(__file__).with_name('prompts').joinpath('welding_v4.md').read_text(encoding='utf-8')
    data = {'detections': rows, 'manual_observations': list(observations),
            'detection_confidence_usage': '仅辅助定位与选择裁图，不是质量分、合格概率或扣分依据',
            'user_supplied_process_context': context, 'learning_goal': learning_goal,
            'candidate_defect_types': list(DEFECT_TYPES),
            'focus_confidence_threshold': FOCUS_CONFIDENCE,
            'focus_regions': regions[:MAX_FOCUS_CROPS],
            'additional_high_confidence_regions_in_overview': regions[MAX_FOCUS_CROPS:],
            'box_coordinate_image_size': [original.width, original.height]}
    content = [{'type': 'text', 'text': prompt + (STREAM_INSTRUCTIONS if stream else '') + json.dumps(data, ensure_ascii=False)},
               {'type': 'text', 'text': '图1：原始图片（未绘制检测框）'}]
    for label, image in [('original', original), ('annotated', annotated)]:
        if label == 'annotated':
            content.append({'type': 'text', 'text': '图2：本地模型检测框参考（框和文字不是缺陷；百分比仅为检测置信度，不是评分）'})
        encoded = base64.b64encode(image_bytes(image)).decode('ascii')
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + encoded}})
    for index, region in enumerate(regions[:MAX_FOCUS_CROPS], 3):
        crop = original.crop(tuple(region['crop_box']))
        crop.thumbnail((960, 960), Image.Resampling.LANCZOS)
        content.append({'type': 'text', 'text': f"图{index}：重点区域（原图裁剪，无检测框）" + json.dumps(region, ensure_ascii=False)})
        content.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image_bytes(crop)).decode('ascii')}})
    return {'model': model, 'messages': [{'role': 'user', 'content': content}],
            'enable_thinking': False, 'stream': stream, 'max_tokens': 3000}


def _stream_content(response, on_dimension):
    """Consume OpenAI-compatible SSE and publish only validated rubric dimensions."""
    buffer, full_text, final_result, received = '', '', None, set()
    try:
        # SSE is UTF-8 even when a server omits charset in Content-Type.
        # Letting requests guess the encoding can corrupt Chinese rubric names.
        lines = response.iter_lines(decode_unicode=False)
    except (AttributeError, TypeError):
        raise AnalysisError('分析服务不支持流式响应，请重试。') from None
    for raw_line in lines:
        if not raw_line:
            continue
        line = raw_line.decode('utf-8', errors='replace') if isinstance(raw_line, bytes) else raw_line
        if not line.startswith('data:'):
            continue
        packet = line[5:].strip()
        if packet == '[DONE]':
            break
        try:
            chunk = json.loads(packet)
            choice = chunk.get('choices', [{}])[0]
            if choice.get('finish_reason') == 'length':
                raise AnalysisError('分析结果被截断，未生成完整报告，请重试。')
            delta = choice.get('delta', {}).get('content', '')
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            continue
        if not isinstance(delta, str):
            continue
        buffer += delta
        full_text += delta
        if len(full_text) > 40000:
            raise AnalysisError('分析服务返回内容过长，请重试。')
        while '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except (ValueError, TypeError):
                continue
            if not isinstance(event, dict):
                continue
            if event.get('type') == 'dimension':
                name, score, reason = event.get('name'), event.get('score'), event.get('reason')
                maximum = dict(DIMENSIONS).get(name)
                if (maximum is None or name in received or
                        (score is not None and (type(score) is not int or not 0 <= score <= maximum)) or
                        not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 24):
                    continue
                received.add(name)
                on_dimension(name, {'分数': score, '理由': reason.strip()})
            elif event.get('type') == 'report' and isinstance(event.get('result'), dict):
                final_result = event['result']
    tail = buffer.strip()
    if tail:
        try:
            event = json.loads(tail)
            if isinstance(event, dict) and event.get('type') == 'report' and isinstance(event.get('result'), dict):
                final_result = event['result']
            elif isinstance(event, dict) and event.get('type') == 'dimension':
                name, score, reason = event.get('name'), event.get('score'), event.get('reason')
                maximum = dict(DIMENSIONS).get(name)
                if (maximum is not None and name not in received and
                        (score is None or type(score) is int and 0 <= score <= maximum) and
                        isinstance(reason, str) and 0 < len(reason.strip()) <= 24):
                    received.add(name)
                    on_dimension(name, {'分数': score, '理由': reason.strip()})
        except (ValueError, TypeError):
            pass
    if final_result is None:
        # Compatible endpoints may stream a single JSON document instead of NDJSON.
        try:
            candidate = json.loads(full_text.strip())
            if isinstance(candidate, dict):
                final_result = candidate
        except (ValueError, TypeError):
            pass
    if final_result is None:
        raise AnalysisError('分析服务连接中断，未收到完整评价结果，请重试。')
    try:
        final_dimensions = final_result['六维评分']
        for name, _ in DIMENSIONS:
            item = final_dimensions.get(name) if isinstance(final_dimensions, dict) else None
            maximum = dict(DIMENSIONS).get(name)
            if (name not in received and isinstance(item, dict)
                    and (item.get('分数') is None or type(item.get('分数')) is int and 0 <= item.get('分数') <= maximum)
                    and isinstance(item.get('理由'), str) and 0 < len(item['理由'].strip()) <= 24):
                on_dimension(name, {'分数': item.get('分数'), '理由': item['理由'].strip()})
    except (KeyError, AttributeError, TypeError):
        pass
    return final_result


def parse_analysis(value):
    if isinstance(value, dict):
        result = value
    elif isinstance(value, str) and len(value) <= 30000:
        text = value.strip()
        if text.startswith('```') and text.endswith('```'):
            text = re.sub(r'^```(?:json)?\s*', '', text, count=1).removesuffix('```').strip()
        try:
            result = json.loads(text)
        except (ValueError, TypeError):
            raise AnalysisError('分析服务未返回完整的分类与教学报告，请重试；本地检测结果仍保留。') from None
    else:
        raise AnalysisError('分析服务返回的内容无效或过长，请重试。')
    if not isinstance(result, dict) or set(result) != set(SECTIONS) | {'本次评分', '六维评分'}:
        raise AnalysisError('分析服务返回的栏目不完整，请重试。')
    score = result['本次评分']
    if not isinstance(score, dict) or set(score) != {'理由'}:
        raise AnalysisError('分析服务未返回完整的本次评分，请重试。')
    reason = score['理由']
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 40:
        raise AnalysisError('分析服务未返回简短的评分理由，请重试。')
    score['理由'] = reason.strip()
    for section in SECTIONS:
        items = result[section]
        if isinstance(items, str):
            items = [items]
        limit = 3 if section == '缺陷类型' else 1
        if (not isinstance(items, list) or not 1 <= len(items) <= limit
                or any(not isinstance(item, str) or not item.strip() or len(item) > 40 for item in items)):
            raise AnalysisError('分析服务未按简短教学反馈格式返回，请重试。')
        result[section] = [item.strip() for item in items]
    if sum(len(item) for section in SECTIONS for item in result[section]) + len(score['理由']) > 220:
        raise AnalysisError('分析服务未按简短教学反馈格式返回，请重试。')
    try:
        result['六维评分'], calculated = evaluate_quality(
            result['六维评分'], result['缺陷类型'], result['图中现象'])
    except ValueError as exc:
        raise AnalysisError(str(exc)) from None
    score.update(calculated)
    return result


def analyze(original, annotated, rows, observations, context, config, *, learning_goal=DEFAULT_LEARNING_GOAL,
            transport=None, on_dimension=None):
    if not config.api_key.strip():
        raise AnalysisError('请先打开右上角“设置”，填写 API Key。')
    url = endpoint_url(config.endpoint)
    streaming = on_dimension is not None
    payload = make_payload(original, annotated, rows, observations, context, config.model.strip(), learning_goal,
                           stream=streaming)
    post = transport or requests.post
    try:
        response = post(url, headers={'Authorization': 'Bearer ' + config.api_key.strip(),
            'Content-Type': 'application/json'}, json=payload, timeout=(10, 180), allow_redirects=False,
            stream=streaming)
    except requests.Timeout:
        raise AnalysisError('分析请求超时，请稍后重试；不会自动重复请求。') from None
    except requests.RequestException:
        raise AnalysisError('无法连接分析服务，请检查网络和接口地址。') from None
    try:
        if response.status_code != 200:
            messages = {
                400: '请求参数不被支持，请检查模型是否支持图片和非思考模式，以及接口地域是否正确。',
                401: 'API Key 验证失败，请检查密钥及所属地域。',
                403: '当前账号没有该模型的调用权限，请在百炼控制台检查。',
                404: '模型或接口不存在，请核对模型名及控制台提供的地址。',
                429: '接口限流或额度不足，请在百炼控制台检查后重试。',
            }
            raise AnalysisError(messages.get(response.status_code, f'分析服务请求失败（HTTP {response.status_code}），请稍后重试。'))
        try:
            if streaming:
                body = {}
                sections = parse_analysis(_stream_content(response, on_dimension))
            else:
                body = response.json()
                choice = body['choices'][0]
                if choice.get('finish_reason') == 'length':
                    raise AnalysisError('分析结果被截断，未生成完整报告，请重试。')
                sections = parse_analysis(choice['message']['content'])
        except (ValueError, KeyError, TypeError, IndexError):
            raise AnalysisError('分析服务返回格式异常，请重试。') from None
        except requests.Timeout:
            raise AnalysisError('分析响应超时，请稍后重试；不会自动重复请求。') from None
        except requests.RequestException:
            raise AnalysisError('分析服务连接中断，请检查网络后重试。') from None
        usage = body.get('usage', {})
        report = {'provider': '通义千问', 'model': config.model.strip(),
            'learning_goal': learning_goal.strip() or DEFAULT_LEARNING_GOAL,
            'feedback_version': FEEDBACK_VERSION,
            'focus_confidence_threshold': FOCUS_CONFIDENCE,
            'focus_regions': focus_regions(rows, original.size)[:MAX_FOCUS_CROPS],
            'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'score': sections.pop('本次评分'),
            'dimensions': sections.pop('六维评分'),
            'rubric_version': RUBRIC_VERSION,
            'dimension_weights': dict(DIMENSIONS),
            'sections': sections,
            'usage': {key: usage[key] for key in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                      if isinstance(usage, dict) and isinstance(usage.get(key), int)},
            'note': '这是练习参考，具体操作和参数调整请结合老师的指导。'}
        report['audit'] = build_audit(report, payload, original.size, rows)
        return report
    finally:
        response.close()


def report_text(report):
    lines = ['焊接实训学习反馈', f"本次训练目标：{report.get('learning_goal', DEFAULT_LEARNING_GOAL)}",
             f"时间：{report['generated_at']}", '']
    score = report['score']
    value = '暂无法评分' if score['分数'] is None else f"{score['分数']} / 100 分"
    lines.extend(['【本次评分】', value + '（' + score.get('评分类型', '外观练习参考') + '）', score['理由'], ''])
    if '等级' in score:
        for key in ('基础分', '最低项分', '短板惩罚', '最终分', '等级', '是否达到教学目标'):
            lines.append(f'{key}：{score[key] if score[key] is not None else "—"}')
        lines.append('；'.join(score['判定依据']))
        lines.append('评价范围：' + score.get('评价范围', '历史评价'))
        if score.get('关键缺陷'):
            lines.append(f'限分前得分：{score["限分前得分"]}；关键缺陷扣分：{score["关键缺陷扣分"]}；上限：{score["分数上限"]}')
            lines.extend(f'关键缺陷：{item["类型"]}；{item["依据"]}（{item["性质"]}）' for item in score['关键缺陷'])
    if report.get('dimensions'):
        lines.append('【六维评分】')
        for name, weight in report.get('dimension_weights', dict(DIMENSIONS)).items():
            item = report['dimensions'][name]
            raw = item.get('得分', item['分数'])
            maximum = item.get('满分', 100)
            number = '—' if raw is None else f'{raw} / {maximum}'
            radar = 'null' if item['分数'] is None else str(item['分数'])
            lines.append(f'{name} | 权重{weight}% | {number} | 雷达值{radar} | {item["理由"]}')
        lines.extend(['六项完整时基础分A = 六项原始得分之和；缺项时至少4项且覆盖权重≥60%，'
                      '基础分A = 可评项原始得分之和 / 可评项满分之和 × 100，仅作为可见项参考分；'
                      '最低项M = 可评项最低标准化得分；'
                      f'{SCORE_FORMULA}，按四舍五入取整。'
                      f'可评项目不足时不计算总分。完整六项符合需S≥{PASS_SCORE}、所有单项≥{PASS_MINIMUM}，'
                      f'非常符合需S≥{EXCELLENT_SCORE}、所有单项≥{EXCELLENT_MINIMUM}，'
                      '结论仅针对六维外观教学目标。', ''])
    for section in SECTIONS:
        lines.append('【' + section + '】')
        lines.extend(f'{index}. {item}' for index, item in enumerate(report['sections'][section], 1))
        lines.append('')
    lines.append(report['note'])
    if report.get('audit'):
        lines.extend(['', '【运算过程留痕】', '数据与计算一致性：' + ('通过' if all(x['passed'] for x in report['audit']['checks']) else '存在差异'),
                      '请求内容指纹：' + report['audit']['request_sha256'],
                      '图像输入数：' + str(len(report['audit']['images'])),
                      '完整精确计算、图像指纹与校验项见 JSON 报告的 score.计算明细 和 audit。'])
    return '\n'.join(lines)
