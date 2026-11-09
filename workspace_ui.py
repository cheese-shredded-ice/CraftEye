"""Compact, single-screen desktop workspace shared by image and camera modes."""
from collections import Counter
from html import escape
from pathlib import Path

import streamlit as st


def install_layout():
    st.html('<style>' + Path(__file__).with_name('workspace.css').read_text(encoding='utf-8') + '</style>')


def detection_summary(rows):
    counts = Counter(row.get('类别', '缺陷') for row in rows)
    badges = ''.join(f'<span>{escape(name)} <b>{count}</b></span>' for name, count in counts.items())
    st.html('<div class="detection-summary">' + (badges or '<span>未检出目标</span>') + '</div>')


def ai_placeholder(message=''):
    st.subheader('综合分析')
    description = f'<p>{escape(message)}</p>' if message else ''
    st.html(f'<div class="ai-placeholder"><span>✦</span><h3>本次学习反馈</h3>{description}</div>')
