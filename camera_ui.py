"""Single-screen camera workspace with explicit snapshots for AI analysis."""
import io
import json
import time
import uuid

from PIL import Image
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from advice import OBSERVATIONS
from camera import CameraProcessor
from common import MODEL
from inference import get_runner
from ai_ui import render_ai_analysis
from workspace_ui import ai_placeholder, detection_summary, section_heading


@st.fragment(run_every=1.0)
def render_live_results(ctx):
    processor = ctx.video_processor
    playing = ctx.state.playing
    result, error = processor.snapshot() if processor else (None, None)
    paused = st.session_state.get('_camera_paused', False)
    capture = st.session_state.get('camera_capture')
    fresh = not paused and playing and result is not None and time.monotonic() - result.completed_at < 3
    if paused and capture:
        detection_summary(capture['report']['detections'])
    elif not playing:
        st.info('摄像头未运行。')
    elif error:
        st.error(f'实时检测失败：{error}。请停止摄像头后重试。')
    elif result is None:
        st.info('正在等待第一帧检测结果…')
    elif not fresh:
        st.warning('暂未收到新的检测结果，请检查摄像头连接。')
    else:
        st.html(f'<div class="camera-metrics" data-live-threshold="{result.confidence:.2f}"><span>检出区域<b>{len(result.rows)}</b></span><span>处理耗时<b>{result.elapsed_ms:.0f} ms</b></span><span>已处理帧数<b>{result.processed_frames}</b></span></div>')
        detection_summary(result.rows)
    take, preview = st.columns(2)
    with take:
        if paused:
            clicked = False
            if st.button('重新拍摄', key='resume_camera', type='primary', use_container_width=True):
                st.session_state['_camera_paused'] = False
                st.session_state['_camera_start_requested'] = True
                st.session_state.pop('camera_capture', None)
                st.rerun()
        else:
            clicked = st.button('截取当前结果', disabled=not fresh, key='capture_camera_result', use_container_width=True)
    if clicked:
        output, original_output = io.BytesIO(), io.BytesIO()
        result.image.save(output, format='PNG')
        result.original.save(original_output, format='PNG')
        st.session_state['camera_capture'] = {
            'id': uuid.uuid4().hex, 'png': output.getvalue(), 'original_png': original_output.getvalue(),
            'report': {'source': 'camera', 'captured_at': result.timestamp, 'confidence_threshold': result.confidence,
                'processed_width': result.image.width, 'processed_height': result.image.height,
                'detections': result.rows, 'manual_observations': list(st.session_state.get('camera_observations', []))},
        }
        # Keep the WebRTC component mounted long enough to close its media tracks.
        st.session_state['_camera_paused'] = True
        st.session_state['_camera_start_requested'] = False
        st.rerun()
    with preview, st.popover('快照与下载', disabled=not capture, use_container_width=True):
        if capture:
            old_advice = capture['report'].pop('advice', None)
            if old_advice is not None:
                capture['report'].setdefault('manual_observations', old_advice.get('manual_observations', []))
                capture['id'] = uuid.uuid4().hex
            st.image(capture['png'], width='stretch')
            st.caption('截取时间：' + capture['report']['captured_at'] + f" · 快照阈值：{capture['report']['confidence_threshold']:.0%}")
            st.download_button('保存摄像头检测图', capture['png'], 'camera-result.png', 'image/png', key='download_camera_png_' + capture['id'], on_click='ignore')
            st.download_button('保存摄像头报告', json.dumps(capture['report'], ensure_ascii=False, indent=2), 'camera-report.json', 'application/json', key='download_camera_report_' + capture['id'], on_click='ignore')
        if st.button('清除快照', key='clear_camera_capture', disabled=not capture, use_container_width=True):
            del st.session_state['camera_capture']
            st.session_state['_camera_paused'] = False
            st.session_state['_camera_start_requested'] = False
            st.rerun()
    if capture:
        status = '正在关闭摄像头…' if playing else '摄像头已关闭'
        st.html(f'<div class="detection-summary" data-camera-frozen="true"><span>画面已暂停 · {status}</span></div>')


def render_camera(confidence):
    workspace, feedback = st.columns([1, 2.15], gap='medium')
    with workspace, st.container(key='camera-stage'):
        title, options = st.columns([1, 1])
        with title:
            section_heading('实时画面', 'camera')
        with options, st.popover('现场现象', use_container_width=True):
            st.multiselect('补充摄像头现场现象（可选，人工选择）', list(OBSERVATIONS), key='camera_observations')
        if not MODEL.exists():
            st.warning('请先下载本地模型，再使用摄像头。')
            return
        try:
            runner = get_runner()
        except Exception as exc:
            st.error(f'模型加载失败：{exc}')
            return
        paused = st.session_state.get('_camera_paused', False)
        requested = st.session_state.get('_camera_start_requested', False)
        st.html('<style>.st-key-camera-stream{display:' + ('none' if paused else 'block') + '}</style>')
        with st.container(key='camera-stream'):
            ctx = camera_stream(confidence, runner, False if paused else True if requested else None)
        if requested and ctx.state.playing:
            st.session_state['_camera_start_requested'] = False
        if ctx.video_processor:
            ctx.video_processor.configure(confidence)
        capture = st.session_state.get('camera_capture')
        if paused and capture:
            with st.container(key='camera-freeze'):
                st.image(capture['png'], width='stretch')
        render_live_results(ctx)
    with feedback, st.container(key='camera-ai'):
        capture = st.session_state.get('camera_capture')
        if capture and capture.get('original_png'):
            render_ai_analysis('camera', capture['id'], Image.open(io.BytesIO(capture['original_png'])).convert('RGB'),
                Image.open(io.BytesIO(capture['png'])).convert('RGB'), capture['report']['detections'], capture['report'].get('manual_observations', []))
        else:
            ai_placeholder('截取当前画面后，即可生成评分与教学建议。')


def camera_stream(confidence, runner, desired):
    return webrtc_streamer(
            key='welding-live-camera', mode=WebRtcMode.SENDRECV,
            desired_playing_state=desired,
            rtc_configuration={'iceServers': []},
            media_stream_constraints={'video': {'width': {'ideal': 640, 'max': 960}, 'height': {'ideal': 480, 'max': 720}, 'frameRate': {'ideal': 10, 'max': 15}}, 'audio': False},
            video_processor_factory=lambda: CameraProcessor(runner, confidence), async_processing=True,
            video_html_attrs={'autoPlay': True, 'controls': False, 'muted': True, 'playsInline': True,
                              'style': {'width': '100%', 'height': '260px', 'objectFit': 'contain', 'background': '#f4f6f8', 'borderRadius': '8px'}},
            translations={
                'start': '开始实时识别', 'stop': '停止摄像头', 'select_device': '选择摄像头', 'select_camera': '摄像头',
                'device_ask_permission': '请允许浏览器使用摄像头',
                'device_not_available': '未找到可用摄像头，请连接设备后重试',
                'device_access_denied': '摄像头权限被拒绝，请在浏览器地址栏的站点设置中允许访问',
                'media_api_not_available': '浏览器无法访问摄像头，请使用 Chrome/Edge 打开 http://127.0.0.1:8501',
            }, media_toggle_controls=False,
        )
