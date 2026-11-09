import io
import json
import hashlib

import pandas as pd
from PIL import Image, ImageOps
import streamlit as st

from common import ROOT, DATASET, MODEL, CLASS_NAMES, CHINESE_NAMES, COLORS
from advice import OBSERVATIONS, build_advice, advice_text
from inference import draw_boxes, infer
from ai_ui import render_ai_settings, render_ai_analysis

st.set_page_config(page_title='焊接缺陷识别', page_icon='🔎', layout='wide')
st.title('焊接缺陷识别')
st.caption('本地运行 · 图片检测 · 摄像头实时识别')



with st.sidebar:
    st.header('运行状态')
    if MODEL.exists():
        st.success('本地模型已就绪')
    else:
        st.warning('模型尚未下载；请先运行安装环境.bat。')
    st.write('三类标签：焊接不良、焊接良好、缺陷。')
    st.caption('“缺陷”是数据集中的统称，不能进一步区分裂纹、气孔等具体类型。')
    confidence = st.slider('检测置信度阈值', 0.05, 0.95, 0.25, 0.05)
    st.caption('未检出目标不代表焊接合格；结果用于学习和验证。')
    render_ai_settings()

detect_tab, camera_tab, browse_tab, info_tab = st.tabs(['图片识别', '摄像头实时识别', '浏览数据与标注', '模型与说明'])

with detect_tab:
    upload = st.file_uploader('上传一张焊接图片', type=['jpg', 'jpeg', 'png', 'bmp', 'webp'])
    samples = sorted((DATASET / 'test' / 'images').glob('*.jpg'))
    sample = st.selectbox('或选用测试集图片', samples, format_func=lambda p: p.name, index=None,
                          placeholder='选择示例图片')
    source = upload if upload is not None else sample
    if source is not None:
        try:
            image = ImageOps.exif_transpose(Image.open(source)).convert('RGB')
            left, right = st.columns(2)
            with left:
                st.image(image, caption='输入图片', width='stretch')
            fingerprint = hashlib.sha256(image.tobytes() + str((image.size, confidence,
                MODEL.stat().st_mtime_ns if MODEL.exists() else None)).encode()).hexdigest()
            observations = st.multiselect('补充现场现象（可选，人工选择）', list(OBSERVATIONS),
                key='observations_' + fingerprint,
                help='模型不会自动识别这些细分现象。选择后，建议将按你提供的信息筛选；不选择也会给出通用排查项。')
            if st.button('开始识别', type='primary', disabled=not MODEL.exists()):
                with st.spinner('正在识别…'):
                    annotated, rows = infer(image, confidence)
                st.session_state['detection'] = {'fingerprint': fingerprint, 'image': annotated, 'rows': rows}
            detection = st.session_state.get('detection')
            if detection and detection['fingerprint'] == fingerprint:
                annotated, rows = detection['image'], detection['rows']
                with right:
                    st.image(annotated, caption='模型检测结果', width='stretch')
                if rows:
                    st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
                else:
                    st.info('在当前阈值下未检出目标。')
                advice = build_advice([CHINESE_NAMES.index(row['类别']) for row in rows], observations)
                st.subheader('可能原因与调整建议')
                st.write(advice['summary'])
                st.caption(advice['limitation'])
                if advice['recommendations']:
                    st.write(advice['basis'])
                    for index, item in enumerate(advice['recommendations'], 1):
                        with st.expander(f"排查 {index}：{item['排查方向']}", expanded=bool(observations) or index == 1):
                            st.write('**需核实的现象：** ' + item['需核实的现象'])
                            st.write('**可能原因：** ' + item['可能原因'])
                            st.write('**调整建议：** ' + item['调整建议'])
                st.info(advice['method'])
                output = io.BytesIO()
                annotated.save(output, format='PNG')
                st.download_button('保存检测图片', output.getvalue(), 'welding-result.png', 'image/png')
                st.download_button('保存检测数据', json.dumps(rows, ensure_ascii=False, indent=2),
                                   'welding-result.json', 'application/json')
                st.download_button('保存建议说明', advice_text(advice), 'welding-advice.txt', 'text/plain')
                report = {'detections': rows, 'confidence_threshold': confidence, 'advice': advice}
                st.download_button('保存完整报告', json.dumps(report, ensure_ascii=False, indent=2),
                                   'welding-report.json', 'application/json')
                render_ai_analysis('image', fingerprint, image, annotated, rows, observations)
        except (OSError, ValueError) as exc:
            st.error(f'图片读取或处理失败：{exc}')
    else:
        st.info('上传图片或选择一张测试集图片，然后点击“开始识别”。')

with camera_tab:
    from camera_ui import render_camera
    render_camera(confidence)

with browse_tab:
    split = st.selectbox('数据分组', ['train', 'valid', 'test'],
                         format_func=lambda s: {'train': '训练集', 'valid': '验证集', 'test': '测试集'}[s])
    files = sorted((DATASET / split / 'images').glob('*.jpg'))
    st.write(f'本组共 {len(files)} 张图片。显示的方框来自数据集人工标注。')
    if files:
        index = st.number_input('图片序号', min_value=1, max_value=len(files), value=1)
        selected = files[index - 1]
        original = Image.open(selected).convert('RGB')
        boxes, rows = [], []
        label = DATASET / split / 'labels' / (selected.stem + '.txt')
        for line in label.read_text().splitlines():
            cls, x, y, w, h = map(float, line.split())
            coords = ((x-w/2)*original.width, (y-h/2)*original.height,
                      (x+w/2)*original.width, (y+h/2)*original.height)
            boxes.append((int(cls), coords, None))
            rows.append({'类别': CHINESE_NAMES[int(cls)], '原始标签': CLASS_NAMES[int(cls)]})
        st.image(draw_boxes(original, boxes), caption=selected.name, width=650)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True)

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
        st.caption('以上为数据集原始测试分组结果。相近视频帧可能跨组出现，不能据此推断实际产线精度。')
    st.write('无需训练。双击“启动焊接识别.bat”即可打开本地识别界面。')
    st.write('识别后提供电流、焊枪角度和行走速度等条件式排查建议；可人工补充现场现象以筛选建议。原因未经模型验证。')
    st.write('详细操作、命令和环境版本见项目文件夹内的 README.md。')
