"""Session-local AI configuration, explicit submission, and asynchronous reports."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os

import streamlit as st

from ai_analysis import (AIConfig, AnalysisError, DEFAULT_ENDPOINT, DEFAULT_MODEL,
                         SECTIONS, analysis_identity, analyze, report_text)


def current_config():
    return AIConfig(
        api_key=st.session_state.get('qwen_api_key', '').strip() or os.environ.get('DASHSCOPE_API_KEY', ''),
        endpoint=st.session_state.get('qwen_endpoint', DEFAULT_ENDPOINT),
        model=st.session_state.get('qwen_model', DEFAULT_MODEL),
    )


def render_ai_settings():
    with st.expander('通义千问 AI 设置', expanded=False):
        st.text_input('API Key', type='password', key='qwen_api_key',
                      help='只保留在当前浏览器会话，不写入项目文件。也可使用本机 DASHSCOPE_API_KEY 环境变量。')
        st.text_input('视觉模型', value=os.environ.get('DASHSCOPE_MODEL', DEFAULT_MODEL), key='qwen_model')
        st.text_input('接口地址', value=os.environ.get('DASHSCOPE_BASE_URL', DEFAULT_ENDPOINT), key='qwen_endpoint',
                      help='以百炼控制台提供的地域/工作空间地址为准，需以 /compatible-mode/v1 结尾。')
        st.caption('支持百炼工作空间专属地址。模型和 API Key 必须属于所选地域。')
        st.markdown('[获取 API Key](https://help.aliyun.com/zh/model-studio/get-api-key) · '
                    '[通义千问视觉模型文档](https://help.aliyun.com/zh/model-studio/vision)')
        if current_config().api_key:
            st.caption('密钥已配置，调用权限将在分析时验证。')
        else:
            st.caption('尚未配置密钥；本地图片和摄像头检测仍可使用。')


@st.cache_resource
def get_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix='welding-visual-ai')


@st.fragment(run_every=1.0)
def render_ai_analysis(namespace, source_id, original, annotated, rows, observations):
    st.subheader('AI 综合分析')
    st.caption('点击下方按钮，将本张原图、检测框图、检测结果和补充信息发送至通义千问，按你的 API 套餐计费。不会自动上传视频。')
    context = st.text_area('补充工艺信息（可选）', key=f'ai_context_{namespace}_{source_id}', max_chars=2000,
        placeholder='例如：MAG 焊、碳钢、板厚 3 mm、电流 120 A、电压 20 V；不确定的参数可以留空。',
        help='这些是你提供的现场信息，AI 不会把它们当作图片测量结果。')
    config = current_config()
    identity = analysis_identity(original, annotated, rows, observations, context, config)
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
            st.session_state[error_key] = {'identity': job['identity'], 'message': 'AI 分析未完成，请稍后重试。'}
        del st.session_state[job_key]
        job = None
    if st.button('AI 综合分析当前图片', key=f'ai_submit_{namespace}', type='primary',
                 disabled=bool(job) or not config.api_key):
        inputs = {'source_id': source_id, 'source_type': namespace, 'detections': copy.deepcopy(rows),
                  'manual_observations': list(observations), 'process_context': context.strip(),
                  'original_size': [original.width, original.height]}
        future = get_executor().submit(analyze, original.copy(), annotated.copy(),
                                        copy.deepcopy(rows), list(observations), context, config)
        st.session_state[job_key] = {'identity': identity, 'future': future, 'inputs': inputs}
        st.session_state.pop(error_key, None)
        # Disable the submit button immediately; never resubmit during periodic refreshes.
        st.rerun(scope='fragment')
    if job:
        if job['identity'] == identity:
            st.info('通义千问正在分析这张图片，请稍候…')
        else:
            st.info('上一份输入的分析仍在进行。完成后可分析当前图片；旧结果不会应用到新输入。')
    if not config.api_key:
        st.info('请展开左侧“通义千问 AI 设置”填写 API Key，再点击分析按钮。')
    error = st.session_state.get(error_key)
    if error and error['identity'] == identity:
        st.error(error['message'])
    completed = st.session_state.get(result_key)
    if completed and completed['identity'] == identity:
        report = completed['report']
        st.caption(f"通义千问 · {report['model']} · {report['generated_at']}")
        for section in SECTIONS:
            st.markdown('**【' + section + '】**')
            for index, item in enumerate(report['sections'][section], 1):
                st.text(f'{index}. {item}')
        st.caption(report['note'])
        download_id = identity + report['generated_at']
        st.download_button('保存 AI 分析（TXT）', report_text(report), 'welding-ai-analysis.txt', 'text/plain',
                           key=f'ai_txt_{namespace}_{download_id}', on_click='ignore')
        st.download_button('保存 AI 完整报告（JSON）',
                           json.dumps({'analysis': report, 'inputs': completed['inputs']}, ensure_ascii=False, indent=2),
                           'welding-ai-report.json', 'application/json', key=f'ai_json_{namespace}_{download_id}', on_click='ignore')
    elif completed and not job:
        st.info('图片、补充信息或模型配置已变化，请点击按钮重新分析当前输入。')
