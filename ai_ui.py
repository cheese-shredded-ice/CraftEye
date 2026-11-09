"""Session-local AI configuration, explicit submission, and asynchronous reports."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import tomllib
import uuid

import streamlit as st

from ai_analysis import (AIConfig, AnalysisError, DEFAULT_ENDPOINT, DEFAULT_MODEL,
                         DEFAULT_LEARNING_GOAL, analysis_identity, analyze, report_text)
from teaching_report_ui import report_html
from recognition_history import save_record


def local_api_key():
    # Reading directly avoids a server restart after the local file is created.
    try:
        with (Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml').open('rb') as source:
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


def analyze_and_record(run_id, namespace, *args, **kwargs):
    report = analyze(*args, **kwargs)
    try:
        save_record(run_id, namespace, report, annotated=args[1] if len(args) > 1 else kwargs.get('annotated'))
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
    future = get_executor().submit(analyze_and_record, uuid.uuid4().hex, namespace, original.copy(), annotated.copy(),
                                    copy.deepcopy(rows), list(observations), context, config,
                                    learning_goal=learning_goal)
    st.session_state[job_key] = {'identity': identity, 'future': future, 'inputs': inputs}
    st.session_state.pop(f'_ai_error_{namespace}', None)
    st.session_state.pop(f'_ai_result_{namespace}', None)
    return True


@st.fragment(run_every=1.0)
def render_ai_analysis(namespace, source_id, original, annotated, rows, observations):
    learning_goal = DEFAULT_LEARNING_GOAL
    context = ''
    config = current_config()
    identity = analysis_identity(original, annotated, rows, observations, context, config, learning_goal)
    job_key, result_key, error_key = (f'_ai_{name}_{namespace}' for name in ('job', 'result', 'error'))
    job = st.session_state.get(job_key)
    if job and job['future'].done():
        try:
            report = job['future'].result()
            st.session_state[result_key] = {'identity': job['identity'], 'report': report,
                'inputs': job['inputs']}
            st.session_state.pop(error_key, None)
        except AnalysisError as exc:
            st.session_state[error_key] = {'identity': job['identity'], 'message': str(exc)}
        except Exception:
            # Do not expose exception bodies or provider errors containing credentials.
            st.session_state[error_key] = {'identity': job['identity'], 'message': '分析未完成，请稍后重试。'}
        del st.session_state[job_key]
        job = None
    title, submit = st.columns([1, 1.35])
    with title:
        st.subheader('综合分析')
    with submit:
        clicked = st.button('综合分析当前图片', key=f'ai_submit_{namespace}', type='primary',
                            disabled=bool(job) or not config.api_key, use_container_width=True)
    if clicked:
        submit_analysis(namespace, source_id, original, annotated, rows, observations)
        # Disable the submit button immediately; never resubmit during periodic refreshes.
        st.rerun(scope='fragment')
    if job:
        if job['identity'] == identity:
            st.info('正在分析当前图片，请稍候…')
        else:
            st.info('上一份输入的分析仍在进行。完成后可分析当前图片；旧结果不会应用到新输入。')
    if not config.api_key:
        st.info('请打开右上角“分析设置”填写 API Key，再点击分析按钮。')
    error = st.session_state.get(error_key)
    if error and error['identity'] == identity:
        st.error(error['message'])
    completed = st.session_state.get(result_key)
    if completed and completed['identity'] == identity:
        report = completed['report']
        if report.get('history_save_error'):
            st.warning('本次结果已生成，但识别记录保存失败，请先下载报告。')
        st.html(report_html(report, original))
        download_id = identity + report['generated_at']
        with st.popover('下载分析报告'):
            st.download_button('保存分析结果（TXT）', report_text(report), 'welding-analysis.txt', 'text/plain',
                               key=f'ai_txt_{namespace}_{download_id}', on_click='ignore')
            st.download_button('保存完整分析报告（JSON）',
                               json.dumps({'analysis': report, 'inputs': completed['inputs']}, ensure_ascii=False, indent=2),
                               'welding-analysis-report.json', 'application/json', key=f'ai_json_{namespace}_{download_id}', on_click='ignore')
    elif completed and not job:
        st.info('图片、现场现象或模型配置已变化，请点击按钮重新分析当前输入。')
