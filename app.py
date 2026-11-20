import io
import json
import hashlib

from PIL import Image, ImageOps
import streamlit as st

from common import ROOT, DATASET, MODEL
from advice import OBSERVATIONS
from inference import draw_boxes, infer, read_annotation
from ai_ui import render_ai_settings, render_ai_analysis, submit_analysis, detection_report
from workspace_ui import (install_layout, detection_summary, render_brand,
                          section_heading)
from image_library_ui import render_image_picker
from engineering_ui import render_engineering_entry

st.set_page_config(page_title='数智评鉴系统', page_icon='🔎', layout='wide', initial_sidebar_state='collapsed')
install_layout()
with st.container(key='dashboard-header'):
    title, settings = st.columns([8.5, 1.5])
    with title:
        render_brand()
    with settings:
        with st.popover('设置', use_container_width=True):
            if MODEL.exists():
                st.success('本地模型已就绪')
            else:
                st.warning('模型尚未下载；请先运行安装环境.bat。')
            st.slider('检测置信度阈值', min_value=0.05, max_value=0.95,
                      value=0.25, step=0.05, key='confidence_threshold',
                      help='只显示达到该置信度的检测框；置信度不是评分。')
            render_ai_settings()
            st.divider()
            render_engineering_entry()

confidence = float(st.session_state.get('confidence_threshold', 0.25))

SHOW_REFERENCE_TABS = False
ENABLE_BEHAVIOR = False
tab_names = ['图片识别', '摄像头实时识别', '识别记录', '浏览数据与标注']
if ENABLE_BEHAVIOR:
    tab_names.append('实训行为')
if SHOW_REFERENCE_TABS:
    tab_names += ['模型与说明']
tabs = st.tabs(tab_names)
detect_tab, camera_tab = tabs[:2]
history_tab = tabs[2]

with detect_tab:
    workspace, feedback = st.columns([1, 2.15], gap='medium')
    with workspace, st.container(key='image-stage'):
        section_heading('焊接图片识别', 'image')
        choose, observe = st.columns(2)
        with choose, st.container(key='choose-image'), st.popover('选择图片', use_container_width=True):
            source = render_image_picker()
        with observe, st.container(key='observe-image'), st.popover('现场现象', use_container_width=True):
            observations = st.multiselect('补充现场现象（可选，人工选择）', list(OBSERVATIONS), key='image_observations')
        image = None
        read_error = None
        if source is not None:
            try:
                with Image.open(source) as opened:
                    image = ImageOps.exif_transpose(opened).convert('RGB')
            except (OSError, ValueError, Image.DecompressionBombError):
                read_error = '图片读取或处理失败：文件已损坏或不是支持的图片，请重新选择。'
        detect, export = st.columns(2)
        with detect:
            submitted = st.button('开始识别', type='primary', disabled=image is None or not MODEL.exists(), use_container_width=True)
        detection = None
        if image is not None:
            try:
                fingerprint = hashlib.sha256(image.tobytes() + str((image.size, confidence,
                    MODEL.stat().st_mtime_ns if MODEL.exists() else None)).encode()).hexdigest()
                if submitted and st.session_state.get('_ai_job_image'):
                    st.info('综合分析正在进行，请等待本次完成后再开始识别。')
                elif submitted:
                    with st.spinner('正在识别…'):
                        annotated, rows = infer(image, confidence)
                    st.session_state['detection'] = {'fingerprint': fingerprint, 'image': annotated, 'rows': rows}
                    submit_analysis('image', fingerprint, image, annotated, rows, observations)
                candidate = st.session_state.get('detection')
                if candidate and candidate['fingerprint'] == fingerprint:
                    detection = candidate
                with export, st.container(key='export-image'), st.popover('下载结果', disabled=detection is None, use_container_width=True):
                    if detection:
                        output = io.BytesIO()
                        detection['image'].save(output, format='PNG')
                        st.download_button('保存检测图片', output.getvalue(), 'welding-result.png', 'image/png')
                        st.download_button('保存检测数据', json.dumps(detection['rows'], ensure_ascii=False, indent=2), 'welding-result.json', 'application/json')
                        report = {'detections': detection['rows'], 'confidence_threshold': confidence, 'manual_observations': observations}
                        report = detection_report('image', fingerprint, report)
                        st.download_button('保存完整报告', json.dumps(report, ensure_ascii=False, indent=2), 'welding-report.json', 'application/json', on_click='ignore')
                view = st.segmented_control('显示画面', ['检测结果', '原图'], default='检测结果', label_visibility='collapsed')
                st.image(detection['image'] if detection and view != '原图' else image, width='stretch')
                if detection:
                    detection_summary(detection['rows'])
            except (OSError, ValueError, RuntimeError, Image.DecompressionBombError) as exc:
                st.error(f'图片读取或处理失败：{exc}')
        else:
            with export:
                st.button('下载结果', disabled=True, use_container_width=True)
            if read_error:
                st.error(read_error)
            else:
                st.html('<div class="ai-placeholder"><span>＋</span><h3>选择一张焊接图片</h3></div>')
    with feedback, st.container(key='image-ai'):
        if detection and image is not None:
            render_ai_analysis('image', fingerprint, image, detection['image'], detection['rows'], observations)
        else:
            render_ai_analysis('image')

with camera_tab:
    from camera_ui import render_camera
    render_camera(confidence)

with history_tab:
    from history_ui import render_history
    render_history()

browse_tab = tabs[3]
with browse_tab:
    split_column, index_column = st.columns([1, 3])
    with split_column:
        split = st.selectbox('数据分组', ['train', 'valid', 'test'],
                             format_func=lambda s: {'train': '训练集', 'valid': '验证集', 'test': '测试集'}[s])
    files = sorted((DATASET / split / 'images').glob('*.jpg'))
    if files:
        with index_column:
            index = st.number_input('图片序号', min_value=1, max_value=len(files), value=1)
        selected = files[index - 1]
        try:
            with Image.open(selected) as opened:
                original = opened.convert('RGB')
        except (OSError, ValueError, Image.DecompressionBombError):
            st.warning('这张数据集图片无法读取，请选择其他序号。')
        else:
            label = DATASET / split / 'labels' / (selected.stem + '.txt')
            try:
                boxes, rows = read_annotation(label, original.size)
            except (OSError, ValueError):
                boxes, rows = [], []
                st.warning('这张图片的标注缺失或损坏，当前仅显示原图。')
            with st.container(key='browse-image'):
                st.image(draw_boxes(original, boxes), width='stretch')
            if rows:
                detection_summary(rows)
    else:
        st.info('当前分组没有可浏览的图片。')

if ENABLE_BEHAVIOR:
    with tabs[4]:
        from behavior_ui import render_behavior
        render_behavior()

if SHOW_REFERENCE_TABS:
    info_tab = tabs[-1]
    with info_tab:
        st.write('来源：[Hugging Face 数据集](https://huggingface.co/datasets/avinashhm/the-welding-defect-dataset-v2)')
        st.write('保留原始分组：训练 1,619 张，验证 283 张，测试 126 张。')
        st.write('原始仓库只有数据；此界面为本地配套程序。直接使用作者已训练好的 YOLOv8 权重。')
        st.write('模型：[avinashhm/welding-defect-yolov8-full-training](https://huggingface.co/avinashhm/welding-defect-yolov8-full-training)')
        report = ROOT / 'models' / 'metrics.json'
        if report.exists():
            m = json.loads(report.read_text(encoding='utf-8'))
            a, b, c = st.columns(3)
            a.metric('测试集 mAP@50', f'{m["mAP50"]:.1%}')
            b.metric('测试集 mAP@50–95', f'{m["mAP50_95"]:.1%}')
            c.metric('模型来源', '作者预训练权重')
        st.write('无需训练。双击“启动焊接识别.bat”即可打开本地识别界面。')
        st.write('识别后可使用综合分析，按【缺陷类型】【图中现象】【可能原因】【改良建议】生成报告；需先配置 API Key。')
        st.write('详细操作、命令和环境版本见项目文件夹内的 README.md。')
