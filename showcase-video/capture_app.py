"""Read-only presentation of archived real results. No inference or API calls."""
from pathlib import Path
import io
import json
import sys
from html import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import streamlit as st
from PIL import Image
import recognition_history
from workspace_ui import install_layout, render_brand, section_heading
from teaching_report_ui import dimensions_html, reference_url
from score_ui import score_html
from history_ui import render_history

recognition_history.HISTORY_DB = ROOT / 'outputs/showcase/history.sqlite3'
st.set_page_config(page_title='CraftEye 展示素材', layout='wide')
install_layout()
st.html('<span hidden data-video-layout></span><style>'
        '[data-testid="stElementContainer"]:has([data-video-layout]){display:none}'
        '.teaching-report{height:calc(100dvh - 400px)}'
        '.st-key-history-table{--history-table-height:calc(100dvh - 420px)}'
        '.st-key-image-ai,.st-key-history-table,.st-key-history-growth{height:calc(100dvh - 190px);min-height:0}'
        '</style>')
with st.container(key='dashboard-header'):
    a, b = st.columns([8, 2])
    with a:
        render_brand()
    with b:
        st.button('设置')
tabs = st.tabs(['图片识别', '摄像头实时识别', '识别记录'])
sequence = int(st.query_params.get('record', '82'))
record = next(r for r in recognition_history.load_records() if r['sequence'] == sequence)
image = Image.open(io.BytesIO(recognition_history.load_record_images([record['run_id']], full_size=True)[record['run_id']]))
with tabs[0]:
    left, right = st.columns([1, 2.15])
    with left, st.container(key='image-stage'):
        section_heading('焊接图片识别', 'image')
        a, b = st.columns(2)
        with a:
            st.button('选择图片', use_container_width=True)
        with b:
            st.button('现场现象', use_container_width=True)
        a, b = st.columns(2)
        with a:
            st.button('开始识别', type='primary', use_container_width=True)
        with b:
            st.button('下载结果', use_container_width=True)
        st.segmented_control('显示画面', ['检测结果', '原图'], default='检测结果', label_visibility='collapsed')
        st.image(image, width='stretch')
    with right, st.container(key='image-ai'):
        section_heading('综合分析')
        view = st.query_params.get('view', 'radar')
        score = score_html(record['assessment'])
        if view == 'radar':
            content = '<div class="radar-card">' + dimensions_html(record['dimensions']) + '</div>'
        else:
            # Only fields actually saved in the archive are displayed.
            content = '<div class="analysis-content"><div class="feedback-card">'
            for label, text in [('缺陷类型', '；'.join(record['defects'])), ('改良建议', record['suggestion'])]:
                content += '<div class="feedback-row"><div class="feedback-title">【'+label+'】</div><div class="feedback-text"><p>'+escape(text)+'</p></div></div>'
            content += '</div><div class="reference-grid" style="--reference-count:1"><figure><img src="'+reference_url('crack.jpg')+'"><figcaption>裂纹 · 典型示例</figcaption></figure></div></div>'
        st.html('<div class="teaching-report">'+score+content+'</div>')
        st.segmented_control('结果视图', ['六维评分', '改进建议'], default='六维评分' if view=='radar' else '改进建议', label_visibility='collapsed')
        st.button('下载分析报告')
with tabs[1]:
    st.empty()
with tabs[2]:
    render_history()
