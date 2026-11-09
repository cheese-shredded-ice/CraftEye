"""Streamlit controls and periodically refreshed camera results."""
import io
import json
import time
import uuid

import pandas as pd
import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from advice import OBSERVATIONS, build_advice, advice_text
from camera import CameraProcessor
from common import MODEL, CHINESE_NAMES
from inference import get_runner
from ai_ui import render_ai_analysis


def render_advice(advice):
    st.write(advice['summary'])
    st.caption(advice['limitation'])
    for index, item in enumerate(advice['recommendations'], 1):
        with st.expander(f"排查 {index}：{item['排查方向']}"):
            st.write('**需核实的现象：** ' + item['需核实的现象'])
            st.write('**可能原因：** ' + item['可能原因'])
            st.write('**调整建议：** ' + item['调整建议'])
    if advice['recommendations']:
        st.caption(advice['method'])


@st.fragment(run_every=1.0)
def render_live_results(ctx):
    processor = ctx.video_processor
    playing = ctx.state.playing
    result, error = processor.snapshot() if processor else (None, None)
    fresh = playing and result is not None and time.monotonic()-result.completed_at < 3
    observations = st.session_state.get('camera_observations', [])
    if not playing:
        st.info('摄像头未运行。点击上方“开始实时识别”，并允许浏览器访问摄像头。')
    elif error:
        st.error(f'实时检测失败：{error}。请停止摄像头后重试。')
    elif result is None:
        st.info('摄像头已连接，正在等待第一帧检测结果…')
    elif not fresh:
        st.warning('暂未收到新的检测结果。请检查摄像头连接；必要时停止后重新启动。')
    else:
        a, b, c = st.columns(3)
        a.metric('当前帧检出区域', len(result.rows))
        b.metric('单帧处理耗时', f'{result.elapsed_ms:.0f} ms')
        c.metric('已处理帧数', result.processed_frames)
        st.caption(f'本帧阈值：{result.confidence:.0%}。下表与建议每秒刷新；画面中的检测框随视频更新。')
        if result.rows:
            st.dataframe(pd.DataFrame(result.rows), hide_index=True, width='stretch')
        else:
            st.info('当前帧未检出目标，不代表焊接合格。')
        st.subheader('当前帧的排查建议')
        render_advice(build_advice([CHINESE_NAMES.index(row['类别']) for row in result.rows], observations))

    if st.button('截取当前结果', disabled=not fresh, key='capture_camera_result'):
        # Capture a consistent frame/table/threshold pair, not separately read state.
        advice = build_advice([CHINESE_NAMES.index(row['类别']) for row in result.rows], observations)
        output = io.BytesIO()
        result.image.save(output, format='PNG')
        original_output = io.BytesIO()
        result.original.save(original_output, format='PNG')
        st.session_state['camera_capture'] = {
            'id': uuid.uuid4().hex,
            'png': output.getvalue(),
            'original_png': original_output.getvalue(),
            'report': {'source': 'camera', 'captured_at': result.timestamp,
                'confidence_threshold': result.confidence,
                'processed_width': result.image.width, 'processed_height': result.image.height,
                'detections': result.rows, 'advice': advice},
        }
        st.rerun()  # Refresh the AI panel outside this periodically updated fragment.
    capture = st.session_state.get('camera_capture')
    if capture:
        st.subheader('已截取的结果（固定快照）')
        st.image(capture['png'], width=640)
        download_id = capture['id']
        st.download_button('保存摄像头检测图', capture['png'], 'camera-result.png', 'image/png',
                           key='download_camera_png_' + download_id, on_click='ignore')
        st.download_button('保存摄像头报告', json.dumps(capture['report'], ensure_ascii=False, indent=2),
                           'camera-report.json', 'application/json', key='download_camera_report_' + download_id, on_click='ignore')
        st.download_button('保存摄像头建议', advice_text(capture['report']['advice']), 'camera-advice.txt',
                           'text/plain', key='download_camera_advice_' + download_id, on_click='ignore')
        # Publish the completed snapshot label after all three new download widgets.
        st.caption('截取时间：' + capture['report']['captured_at']
                   + f" · 快照阈值：{capture['report']['confidence_threshold']:.0%}。这是保存时的画面与建议，不随实时画面更新。")
        if st.button('清除快照', key='clear_camera_capture'):
            del st.session_state['camera_capture']
            st.rerun()


def render_camera(confidence):
    st.subheader('摄像头实时识别')
    st.write('点击“开始实时识别”，允许摄像头权限后，将镜头对准焊缝。可在视频控件中选择内置或 USB 摄像头。')
    st.caption('使用左侧置信度阈值。视频在本机处理，麦克风关闭，不自动录制。切换页面标签不会自动关闭摄像头，离开前请点击“停止摄像头”。')
    if not MODEL.exists():
        st.warning('请先下载本地模型，再使用摄像头。')
        return
    try:
        runner = get_runner()
    except Exception as exc:
        st.error(f'模型加载失败：{exc}')
        return
    ctx = webrtc_streamer(
        key='welding-live-camera', mode=WebRtcMode.SENDRECV,
        rtc_configuration={'iceServers': []},
        media_stream_constraints={'video': {'width': {'ideal': 640, 'max': 960},
            'height': {'ideal': 480, 'max': 720}, 'frameRate': {'ideal': 10, 'max': 15}}, 'audio': False},
        video_processor_factory=lambda: CameraProcessor(runner, confidence),
        async_processing=True,
        video_html_attrs={'autoPlay': True, 'controls': False, 'muted': True, 'playsInline': True,
                          'style': {'width': '100%', 'maxHeight': '520px'}},
        translations={
            'start': '开始实时识别', 'stop': '停止摄像头', 'select_device': '选择摄像头',
            'select_camera': '摄像头', 'device_ask_permission': '请允许浏览器使用摄像头',
            'device_not_available': '未找到可用摄像头，请连接设备后重试',
            'device_access_denied': '摄像头权限被拒绝，请在浏览器地址栏的站点设置中允许访问',
            'media_api_not_available': '浏览器无法访问摄像头，请使用 Chrome/Edge 打开 http://127.0.0.1:8501',
        },
        media_toggle_controls=False,
    )
    if ctx.video_processor:
        ctx.video_processor.configure(confidence)
    st.multiselect('补充摄像头现场现象（可选，人工选择）', list(OBSERVATIONS), key='camera_observations',
                   help='这些细分现象由你核实，模型不会自动判定；选择后筛选排查建议。')
    render_live_results(ctx)
    capture = st.session_state.get('camera_capture')
    if capture and capture.get('original_png'):
        from PIL import Image
        render_ai_analysis('camera', capture['id'], Image.open(io.BytesIO(capture['original_png'])).convert('RGB'),
            Image.open(io.BytesIO(capture['png'])).convert('RGB'), capture['report']['detections'],
            capture['report']['advice']['manual_observations'])
    elif capture:
        st.info('请重新截取一次画面，以提供未画框的原图用于 AI 分析。')
    with st.expander('摄像头打不开或画面延迟？'):
        st.write('1. 用 Chrome 或 Edge 访问 http://127.0.0.1:8501，首次使用时允许摄像头权限。')
        st.write('2. 在视频控件中选择正确摄像头；若设备被占用，关闭其他使用摄像头的软件。')
        st.write('3. 当前使用 CPU 推理，更新速度取决于电脑负载。程序会丢弃排队的旧帧，优先识别最新画面。')
        st.write('4. 当前服务仅限本机使用。手机或其他电脑远程访问需要另外配置 HTTPS 和服务地址。')
