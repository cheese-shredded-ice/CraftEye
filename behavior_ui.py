"""CraftEye single-screen observable training-behaviour workspace."""
from html import escape
import hashlib
import json
from pathlib import Path
import uuid
from PIL import ImageDraw

import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from behavior_core import BehaviorConfig, PPE_LABELS
from behavior_inference import missing_models
from behavior_video import BehaviorCameraProcessor, OUTPUT, VideoJob, inspect_video
from workspace_ui import section_heading

ROOT = Path(__file__).parent
SAMPLES = {
    '焊接车间 · 装备与姿态': ROOT/'outputs/behavior-samples/workshop-demo.mp4',
    '学校实训 · 独立场景': ROOT/'outputs/behavior-samples/college-welding.mp4',
    '低光焊接 · 可观察性测试': ROOT/'outputs/behavior-samples/mig-welding.webm',
}


def _time(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds//60:02d}:{seconds%60:02d}'


def report_html(report):
    if not report:
        return ('<div class="behavior-empty"><h3>实训行为观察</h3>'
                '<p>选择视频或开启摄像头，查看工位停留、姿态和防护用品。</p>'
                '<p>记录可观察行为，不推测心理专注程度。</p></div>')
    total, latest = report['totals'], report['latest'] or {}
    location = {'inside': '工位区域内', 'outside': '工位区域外', 'unknown': '暂无法判断'}.get(latest.get('location'), '尚无画面')
    coverage = report['coverage_percent']
    metrics = [('观察时长', _time(total['duration'])), ('可观察覆盖率', f'{coverage:.0f}%' if coverage is not None else '—'),
               ('区域外时长', f"{total['outside']:.1f} 秒"), ('姿态可测时长', f"{total['pose_observed']:.1f} 秒"),
               ('倾角偏大时长', f"{total['lean']:.1f} 秒"), ('持续事件', str(len(report['events'])))]
    cards = ''.join(f'<div><span>{k}</span><strong>{v}</strong></div>' for k, v in metrics)
    ppe = latest.get('ppe', {})
    gear = ''.join(f'<div class="gear-{escape(value)}"><b>{escape(name)}</b><span>{PPE_LABELS[value]}</span></div>' for name, value in ppe.items())
    rows = ''.join(f'<tr><td>{_time(e["start"])}–{_time(e["end"])}</td><td>{escape(e["label"])}</td><td>{e["seconds"]:.1f}s</td></tr>' for e in report['events'][-100:])
    events = '<table><tbody>'+rows+'</tbody></table>' if rows else '<p>暂无达到持续时长阈值的事件</p>'
    tips = ''.join(f'<p>{escape(tip)}</p>' for tip in report['suggestions'])
    return (f'<div class="behavior-report"><div class="behavior-state">{location}<span>{escape(report["config"]["phase"])}</span></div>'
            f'<div class="behavior-metrics">{cards}</div><div class="behavior-gear">{gear}</div>'
            '<div class="behavior-note">装备检出不代表正确佩戴；未观察到不作违规判定。</div>'
            f'<h4>行为事件</h4><div class="behavior-events">{events}</div><div class="behavior-tips">{tips}</div></div>')


@st.cache_data(show_spinner=False, max_entries=6)
def video_preview(path, modified):
    return inspect_video(path)


@st.fragment(run_every=1.)
def render_video_result(source, config):
    job = st.session_state.get('behavior_job')
    snapshot = job.snapshot() if job else None
    left, right = st.columns([1.15, 1], gap='medium')
    with left, st.container(key='behavior-preview'):
        section_heading('训练过程', 'camera')
        if snapshot:
            state = snapshot['status']
            if state in {'queued', 'running'}:
                st.progress(snapshot['progress'], text=f"正在分析 · {snapshot['progress']:.0%}")
                if snapshot['image']:
                    st.image(snapshot['image'], width='stretch')
                if st.button('取消本次分析', key='behavior_cancel'):
                    job.cancel.set()
            elif state == 'done':
                report = snapshot['report']
                events = report['events']
                start = 0
                if events:
                    selected = st.selectbox('事件回放', ['完整视频'] + [f'{_time(e["start"])} · {e["label"]}' for e in events], key='behavior_seek_'+job.root.name)
                    if selected != '完整视频':
                        start = next(int(e['start']) for e in events if selected == f'{_time(e["start"])} · {e["label"]}')
                st.video(str(job.root/'annotated.mp4'), start_time=start)
                a, b = st.columns(2)
                with a:
                    st.download_button('下载行为报告', json.dumps(report, ensure_ascii=False, indent=2), '实训行为报告.json', 'application/json', key='behavior_download_report')
                with b:
                    st.download_button('下载标注视频', (job.root/'annotated.mp4').read_bytes(), '实训行为标注.mp4', 'video/mp4', key='behavior_download_video')
            elif state == 'error':
                st.error(snapshot['error'])
            else:
                st.info('本次分析已取消，可以重新开始。')
            # Enable the parent controls when a background job finishes.
            if state in {'done', 'error', 'cancelled'} and st.session_state.get('behavior_running'):
                st.session_state['behavior_running'] = False
                st.rerun()
        elif source:
            try:
                preview = video_preview(str(source), source.stat().st_mtime_ns)
                image = preview['preview'].copy()
                x1, y1, x2, y2 = config.roi
                ImageDraw.Draw(image).rectangle((x1*image.width, y1*image.height, x2*image.width, y2*image.height), outline='#22d3ee', width=3)
                st.image(image, width='stretch')
                st.caption(f"视频时长 {_time(preview['duration'])} · 分析后可回放标注视频")
            except (OSError, ValueError) as exc:
                st.error(str(exc))
        else:
            st.info('请选择一个视频。')
    with right, st.container(key='behavior-feedback'):
        section_heading('行为习惯观察', 'person')
        st.html(report_html(snapshot['report'] if snapshot else None))


@st.fragment(run_every=1.)
def render_camera_report(ctx):
    processor = ctx.video_processor
    report, image, error = processor.snapshot() if processor else (None, None, None)
    if report:
        st.session_state['behavior_live_processor'] = processor
    saved = st.session_state.get('behavior_camera_saved')
    if error:
        st.error('行为检测失败：'+error)
    st.html(report_html(saved or report))
    if processor and report and not saved:
        end = st.button('结束观察并保存', key='behavior_finish')
        if end or not ctx.state.playing:
            result = processor.finish()
            folder = OUTPUT/uuid.uuid4().hex
            folder.mkdir(parents=True)
            (folder/'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            st.session_state['behavior_camera_saved'] = result
            st.session_state['behavior_camera_image'] = image
            st.session_state['behavior_camera_requested'] = False
            st.rerun()
    if saved:
        st.download_button('下载行为报告', json.dumps(saved, ensure_ascii=False, indent=2), '摄像头行为报告.json', 'application/json', key='behavior_camera_download')


def render_behavior():
    missing = missing_models()
    if missing:
        st.info('行为模型尚未安装。请运行 scripts/setup_behavior.py 下载所需模型。')
        return
    active = bool(st.session_state.get('behavior_running'))
    saved = st.session_state.get('behavior_camera_saved')
    live_processor = st.session_state.get('behavior_live_processor')
    camera_active = bool(st.session_state.get('behavior_camera_requested')) or bool(live_processor and not live_processor.finalized)
    controls, selection, settings = st.columns([1.3, 1.3, .8])
    with controls:
        mode = st.segmented_control('输入方式', ['示例视频', '上传视频', '实时摄像头'], default='示例视频',
                                    key='behavior_mode', disabled=active or camera_active, label_visibility='collapsed') or '示例视频'
    config = st.session_state.get('behavior_config', BehaviorConfig())
    with settings, st.popover('观察设置', use_container_width=True, disabled=active or camera_active):
        phase = st.selectbox('训练阶段', ['操作练习', '准备与检查', '清理与收尾', '教师指导'], key='behavior_phase')
        x = st.slider('工位水平范围（%）', 0, 100, (5, 95), key='behavior_roi_x')
        y = st.slider('工位垂直范围（%）', 0, 100, (5, 95), key='behavior_roi_y')
        angle = st.slider('躯干倾角提示阈值（°）', 10, 85, 45, key='behavior_angle')
        seconds = st.slider('事件最短持续时间（秒）', .5, 10., 2., .5, key='behavior_seconds')
        st.caption('单人、固定机位使用。工位范围以人体框中心判断；倾角是二维画面测量值。')
        if x[0] == x[1] or y[0] == y[1]:
            st.warning('工位区域不能为零。')
        else:
            config = BehaviorConfig((x[0]/100, y[0]/100, x[1]/100, y[1]/100), angle, seconds, phase=phase)
            st.session_state['behavior_config'] = config
    if mode == '实时摄像头':
        with selection:
            if camera_active and st.button('停止当前观察', use_container_width=True):
                if live_processor:
                    report = live_processor.finish()
                    folder = OUTPUT/uuid.uuid4().hex
                    folder.mkdir(parents=True)
                    (folder/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    st.session_state['behavior_camera_saved'] = report
                    st.session_state['behavior_camera_image'] = live_processor.snapshot()[1]
                st.session_state['behavior_camera_requested'] = False
                st.rerun()
            if st.button('开始新一轮观察', disabled=camera_active, use_container_width=True):
                st.session_state.pop('behavior_camera_saved', None)
                st.session_state.pop('behavior_camera_image', None)
                st.session_state.pop('behavior_live_processor', None)
                st.session_state['behavior_camera_session'] = uuid.uuid4().hex
                st.session_state['behavior_camera_requested'] = True
                saved = None
        left, right = st.columns([1.15, 1], gap='medium')
        with left, st.container(key='behavior-preview'):
            section_heading('实训摄像头', 'camera')
            st.html('<style>.st-key-behavior-live{display:'+('none' if saved else 'block')+'}</style>')
            with st.container(key='behavior-live'):
                ctx = webrtc_streamer(key='behavior-camera-'+st.session_state.get('behavior_camera_session', 'initial'),
                    mode=WebRtcMode.SENDRECV,
                    desired_playing_state=st.session_state.get('behavior_camera_requested', False),
                    rtc_configuration={'iceServers': []},
                    media_stream_constraints={'video': {'width': {'ideal': 960}, 'height': {'ideal': 720}, 'frameRate': {'ideal': 10, 'max': 15}}, 'audio': False},
                    video_processor_factory=lambda: BehaviorCameraProcessor(config), async_processing=True,
                    video_html_attrs={'autoPlay': True, 'controls': False, 'muted': True, 'playsInline': True,
                                      'style': {'width': '100%', 'maxHeight': '380px', 'objectFit': 'contain'}},
                    translations={'start': '开启行为摄像头', 'stop': '停止观察', 'select_device': '选择摄像头', 'select_camera': '摄像头'})
            if saved and st.session_state.get('behavior_camera_image'):
                st.image(st.session_state['behavior_camera_image'], width='stretch')
            st.caption('单个学生入镜，镜头覆盖头部、双手与工位。')
        with right, st.container(key='behavior-feedback'):
            section_heading('行为习惯观察', 'person')
            render_camera_report(ctx)
        return
    source = None
    with selection, st.popover('选择训练视频', use_container_width=True, disabled=active):
        if mode == '示例视频':
            available = {label: path for label, path in SAMPLES.items() if path.exists()}
            if available:
                label = st.selectbox('演示视频', list(available), key='behavior_sample')
                source = available[label]
            else:
                st.info('尚未下载示例，可运行 scripts/setup_behavior.py --videos。')
        else:
            uploaded = st.file_uploader('上传训练视频（最长10分钟）', type=['mp4','mov','avi','webm','mkv'], key='behavior_upload')
            if uploaded:
                content = uploaded.getbuffer()
                digest = hashlib.sha256(content).hexdigest()
                folder = OUTPUT/'uploads'
                folder.mkdir(parents=True, exist_ok=True)
                source = folder/(digest+Path(uploaded.name).suffix.lower())
                if not source.exists():
                    source.write_bytes(content)
        st.caption('本地分析，无需联网调用综合分析接口。')
    signature = (str(source), repr(config))
    if not active and signature != st.session_state.get('behavior_source_signature'):
        st.session_state.pop('behavior_job', None)
        st.session_state['behavior_source_signature'] = signature
    # Keep a separate run button below the compact source bar.
    if st.button('开始行为分析', type='primary', disabled=not source or active, key='behavior_start'):
        try:
            inspect_video(source)
            st.session_state['behavior_job'] = VideoJob(source, config).start()
            st.session_state['behavior_running'] = True
            st.rerun()
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    render_video_result(source, config)
