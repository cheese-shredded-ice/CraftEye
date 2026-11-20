"""Compact, single-screen desktop workspace shared by image and camera modes."""
from collections import Counter
from html import escape
from pathlib import Path

import streamlit as st
import base64
from dashboard_visuals import icon_html, icon_url

def install_layout():
    root = Path(__file__).parent
    banner = base64.b64encode((root / 'assets/dashboard/welding-banner.webp').read_bytes()).decode()
    icons = ''.join(f'--icon-{name}:url({icon_url(name)});' for name in ('image', 'camera', 'record', 'analysis', 'play', 'download', 'person'))
    # Style-only st.html uses Streamlit's shared event container, where a fragment
    # can overwrite it. Anchor the stylesheet in the main tree instead.
    st.html('<span data-workspace-style hidden></span><style>:root{--dashboard-banner:url(data:image/webp;base64,' + banner + ');'
            + icons + '}'
            + root.joinpath('workspace.css').read_text(encoding='utf-8') + '</style>')


def render_brand():
    assets = Path(__file__).with_name('assets').joinpath('dashboard')
    logo = base64.b64encode(assets.joinpath('crafteye-logo.png').read_bytes()).decode()
    baic = base64.b64encode(assets.joinpath('baic-logo.svg').read_bytes()).decode()
    st.html('<div class="dashboard-brand"><div class="brand-logo">'
            f'<img src="data:image/png;base64,{logo}" alt="CraftEye 智能焊接评估标志">'
            '<h1>数智评鉴系统</h1></div><div class="partner-logo">'
            f'<img src="data:image/svg+xml;base64,{baic}" alt="BAIC 标志"></div></div>')


def section_heading(title, icon='analysis'):
    st.html('<div class="section-heading">' + icon_html(icon) + f'<h3>{escape(title)}</h3></div>')


def detection_summary(rows):
    counts = Counter(row.get('类别', '缺陷') for row in rows)
    badges = ''.join(f'<span>{icon_html("warning" if name == "缺陷" else "helmet")}{escape(name)} <b>{count}</b></span>' for name, count in counts.items())
    st.html('<div class="detection-summary">' + (badges or '<span>未检出目标</span>') + '</div>')


def ai_placeholder(message='', view='六维评分', include_heading=True, status_message=''):
    from analysis_audit import analysis_status_html
    from teaching_report_ui import dimensions_html
    from score_ui import score_html
    from scoring import DIMENSIONS
    if include_heading:
        section_heading('综合分析')
    description = f'<p>{escape(message)}</p>' if message else ''
    empty_dimensions = {name: {'分数': None, '理由': '-'}
                       for name, _ in DIMENSIONS}
    empty_score = {'分数': 0, '等级': '-', '评分类型': '暂无分析'}
    st.html('<div class="teaching-report">'
            + score_html(empty_score)
            + analysis_status_html(empty=True, message=status_message)
            + '<div class="radar-card">'
            + dimensions_html(empty_dimensions, '暂无分析数据')
            + description + '</div></div>')
