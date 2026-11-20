"""Session-local AI configuration, explicit submission, and asynchronous reports."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
from queue import Empty, Queue
import tomllib
import uuid

import streamlit as st

from .common import ROOT
from .ai_analysis import (AIConfig, AnalysisError, DEFAULT_ENDPOINT, DEFAULT_MODEL,
                         DEFAULT_LEARNING_GOAL, analysis_identity, analyze)
from .teaching_report_ui import report_html
from .recognition_history import save_record
from .workspace_ui import section_heading
from .scoring import DIMENSIONS, evaluate_quality


def local_api_key():
    # Reading directly avoids a server restart after the local file is created.
    try:
        with (ROOT / '.streamlit' / 'secrets.toml').open('rb') as source:
            value = tomllib.load(source).get('DASHSCOPE_API_KEY', '')
        return value.strip() if isinstance(value, str) else ''
    except (OSError, ValueError):
        return ''


def current_config():
    return AIConfig(
        api_key=(st.session_state.get('qwen_api_key', '').strip()
                 or os.environ.get('DASHSCOPE_API_KEY', '').strip() or local_api_key()),
        endpoint=st.session_state.get('qwen_endpoint', DEFAULT_ENDPOINT),
        model=st.session_state.get('qwen_model', DEFAULT_MODEL),
    )


def render_ai_settings():
    st.markdown('**分析设置**')
    st.text_input('API Key', type='password', key='qwen_api_key',
                  help='此处填写的密钥只保留在当前会话；留空则使用本机预设密钥。')
    st.text_input('视觉模型', value=os.environ.get('DASHSCOPE_MODEL', DEFAULT_MODEL), key='qwen_model')
    st.text_input('接口地址', value=os.environ.get('DASHSCOPE_BASE_URL', DEFAULT_ENDPOINT), key='qwen_endpoint',
                  help='以百炼控制台提供的地域/工作空间地址为准，需以 /compatible-mode/v1 结尾。')
    st.markdown('[获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) · '
                '[接口使用说明](https://help.aliyun.com/zh/model-studio/vision)')
    if current_config().api_key:
        st.caption('密钥已配置，调用权限将在分析时验证。')
    else:
        st.caption('尚未配置密钥；本地图片和摄像头检测仍可使用。')

@st.cache_resource
def get_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix='welding-visual-ai')


def analyze_and_record(run_id, namespace, *args, history_inputs=None, **kwargs):
    report = analyze(*args, **kwargs)
    report['run_id'] = run_id
    try:
        save_record(run_id, namespace, report,
                    annotated=args[1] if len(args) > 1 else kwargs.get('annotated'),
                    original=args[0] if args else kwargs.get('original'), inputs=history_inputs)
    except Exception:
        # Keep a successful report usable even when local storage is unavailable.
        report['history_save_error'] = True
    return report


def submit_analysis(namespace, source_id, original, annotated, rows, observations):
    """Start exactly one request for an explicit recognition or analysis action."""
    config = current_config()
    job_key = f'_ai_job_{namespace}'
    if not config.api_key or st.session_state.get(job_key):
        return False
    context, learning_goal = '', DEFAULT_LEARNING_GOAL
    identity = analysis_identity(original, annotated, rows, observations, context, config, learning_goal)
    inputs = {'source_id': source_id, 'source_type': namespace, 'detections': copy.deepcopy(rows),
              'manual_observations': list(observations), 'process_context': context,
              'learning_goal': learning_goal, 'original_size': [original.width, original.height]}
    progress = Queue()
    future = get_executor().submit(analyze_and_record, uuid.uuid4().hex, namespace, original.copy(), annotated.copy(),
                                    copy.deepcopy(rows), list(observations), context, config,
                                    learning_goal=learning_goal, history_inputs=copy.deepcopy(inputs),
                                    on_dimension=lambda name, item: progress.put((name, item)))
    st.session_state[job_key] = {'identity': identity, 'future': future, 'inputs': inputs,
                                 'export_signature': export_signature(source_id, observations, config),
                                 'progress': progress, 'dimensions': {}}
    st.session_state.pop(f'_ai_error_{namespace}', None)
    st.session_state.pop(f'_ai_result_{namespace}', None)
    return True


def export_signature(source_id, observations, config):
    return (source_id, tuple(observations), config.model.strip(), config.endpoint.strip().rstrip('/'))


def detection_report(namespace, source_id, local_report):
    """Include the final analysis only for the exact current detection/configuration."""
    completed = st.session_state.get(f'_ai_result_{namespace}')
    signature = export_signature(source_id, local_report['manual_observations'], current_config())
    if completed and completed.get('export_signature') == signature:
        return {**local_report, 'analysis': completed['report']}
    return local_report


def render_ai_analysis(namespace, source_id='', original=None, annotated=None, rows=None,
                       observations=None, empty_message=''):
    """Render one stable analysis surface for empty, pending, and finished states.

    Keeping the fragment mounted even before an image is available prevents
    Streamlit from leaving the previous placeholder DOM behind when recognition
    starts. That stale DOM was the source of the duplicate score card below the
    live analysis panel.
    """
    # Only pending work needs a timer. Finished reports remain mounted until input changes.
    interval = 1.0 if st.session_state.get(f'_ai_job_{namespace}') else None
    st.fragment(run_every=interval)(_render_ai_analysis)(
        namespace, source_id, original, annotated, rows or [], observations or [], empty_message)


def _render_ai_analysis(namespace, source_id, original, annotated, rows, observations, empty_message=''):
    config = current_config()
    job_key, result_key, error_key = (f'_ai_{name}_{namespace}' for name in ('job', 'result', 'error'))
    job = st.session_state.get(job_key)
    view_key = f'ai_view_{namespace}'
    view = st.session_state.get(view_key, '六维评分')

    # Consume the old task even after its image was removed or replaced. Without
    # this, the empty view stops polling and blocks every later submission.
    if job:
        while True:
            try:
                name, item = job['progress'].get_nowait()
            except Empty:
                break
            job['dimensions'][name] = item
    if job and job['future'].done():
        try:
            report = job['future'].result()
            st.session_state[result_key] = {'identity': job['identity'], 'report': report,
                'inputs': job['inputs'], 'export_signature': job.get('export_signature')}
            st.session_state.pop(error_key, None)
        except AnalysisError as exc:
            st.session_state[error_key] = {'identity': job['identity'], 'message': str(exc)}
        except Exception:
            st.session_state[error_key] = {'identity': job['identity'], 'message': '分析未完成，请稍后重试。'}
        del st.session_state[job_key]
        st.rerun()

    # Keep the heading, action, and view controls mounted in the same order
    # before recognition, while analysis is running, and after it completes.
    title, submit = st.columns([1.7, 1])
    with title:
        section_heading('综合分析')
    with submit:
        clicked = st.button('综合分析当前图片', key=f'ai_submit_{namespace}', type='primary',
                            disabled=original is None or bool(job) or not config.api_key,
                            use_container_width=True)
    if original is None:
        # The empty view keeps the same controls and report slot as a real result.
        from .workspace_ui import ai_placeholder
        ai_placeholder(empty_message, view=view, include_heading=False)
        st.segmented_control('评价视图', ['六维评分', '改进建议'], default=view,
                             label_visibility='collapsed', key=view_key, width='stretch')
        return

    learning_goal = DEFAULT_LEARNING_GOAL
    context = ''
    identity = analysis_identity(original, annotated, rows, observations, context, config, learning_goal)
    if clicked:
        submit_analysis(namespace, source_id, original, annotated, rows, observations)
        # Re-register with a timer and disable submission while the job is pending.
        st.rerun()
    error = st.session_state.get(error_key)
    completed = st.session_state.get(result_key)
    if job and job['identity'] == identity:
        partial = partial_report(job['dimensions'], learning_goal)
        st.html(report_html(partial, original, view, job['inputs']))
    elif completed and completed['identity'] == identity:
        report = completed['report']
        if report.get('history_save_error'):
            st.warning('本次结果已生成，但识别记录保存失败。')
        st.html(report_html(report, original, view, completed['inputs']))
    else:
        from .workspace_ui import ai_placeholder
        notice = ''
        if job:
            notice = '上一份输入的分析仍在进行，完成后可分析当前图片。'
        elif error and error['identity'] == identity:
            notice = error['message']
        elif not config.api_key:
            notice = '请打开右上角“设置”填写 API Key，再点击分析按钮。'
        elif completed:
            notice = '图片、现场现象或模型配置已变化，请点击按钮重新分析当前输入。'
        ai_placeholder(view=view, include_heading=False, status_message=notice)

    # Keep the view switcher at the bottom of the panel in every state.  It is
    # deliberately mounted after the report so recognition never moves it.
    st.segmented_control('评价视图', ['六维评分', '改进建议'], default=view,
                         label_visibility='collapsed', key=view_key, width='stretch')


def partial_report(received, learning_goal):
    """Build a display-only snapshot; accumulate raw points until the final grade."""
    raw = {name: received.get(name, {'分数': None, '理由': '等待识别'}) for name, _ in DIMENSIONS}
    normalized, score = evaluate_quality(raw)
    stage_score = sum(item['分数'] or 0 for item in raw.values())
    score.update({'分数': stage_score, '最终分': None, '等级': '分析中',
                  '是否达到教学目标': '分析中', '达标': False,
                  '评分类型': '分析进度参考', '关键缺陷': [], '计算明细': None,
                  '基础分': None, '短板惩罚': None, '最低项分': None})
    return {'score': score, 'dimensions': normalized, 'dimension_weights': dict(DIMENSIONS),
            'sections': {key: ['分析完成后显示'] for key in ('缺陷类型', '图中现象', '可能原因', '改良建议')},
            'learning_goal': learning_goal, 'streaming': True, 'focus_regions': []}
