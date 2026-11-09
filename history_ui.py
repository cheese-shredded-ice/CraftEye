"""Paginated history table and score trend for the presentation workspace."""
import csv
import base64
from datetime import datetime
from html import escape
import io

import altair as alt
import pandas as pd
import streamlit as st

from recognition_history import load_records, load_record_images
from training_trends import summary_html

PAGE_SIZE = 5


def display_time(value):
    try:
        return datetime.fromisoformat(value).strftime('%m-%d %H:%M')
    except (ValueError, TypeError):
        return value


def defect_label(items):
    return '、'.join(item.split('：', 1)[0].split(':', 1)[0] for item in items)


def export_csv(records):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['序号', '识别时间', '来源', '分数', '缺陷类型', '评分理由', '改良建议'])
    for record in records:
        values = [record['sequence'], record['generated_at'], '摄像头' if record['source_type'] == 'camera' else '图片',
                  record['score'] if record['score'] is not None else '暂无法评分',
                  '；'.join(record['defects']), record['reason'], record['suggestion']]
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value for value in values])
    return output.getvalue().encode('utf-8-sig')


@st.fragment(run_every=2.0)
def render_history():
    try:
        records = load_records()
    except Exception:
        st.error('识别记录暂时无法读取，请检查本地存储。')
        return
    left, right = st.columns([1.1, 1.2], gap='medium')
    with left, st.container(key='history-table'):
        title, download = st.columns([1.5, 1])
        with title:
            st.subheader('识别记录表')
        with download:
            st.download_button('导出记录', export_csv(records), '识别记录.csv', 'text/csv', disabled=not records, on_click='ignore')
        if not records:
            st.html('<div class="history-empty">暂无记录<br>完成一次综合分析后自动保存</div>')
        else:
            pages = (len(records) + PAGE_SIZE - 1) // PAGE_SIZE
            page = min(st.session_state.get('history_page', 1), pages)
            st.session_state['history_page'] = page
            visible = list(reversed(records))[(page-1)*PAGE_SIZE:page*PAGE_SIZE]
            images = load_record_images([record['run_id'] for record in visible])
            rows = []
            for record in visible:
                score = record['score']
                color = '#64748b' if score is None else '#dc2626' if score < 60 else '#b45309' if score < 80 else '#15803d'
                score_text = '—' if score is None else str(score)
                source = '摄像头' if record['source_type'] == 'camera' else '图片'
                image_data = images.get(record['run_id'])
                picture = (f'<img class="history-thumbnail" src="data:image/png;base64,{base64.b64encode(image_data).decode("ascii")}" alt="第{record["sequence"]}次 YOLO 检测结果">'
                           if image_data else '<span class="history-no-image">暂无图片</span>')
                rows.append(f'<tr><td title="{escape(record["generated_at"], quote=True)} · {source}">{record["sequence"]}</td><td>{picture}</td>'
                            f'<td>{escape(defect_label(record["defects"]))}</td><td style="color:{color}" title="{escape(record["reason"], quote=True)}"><b>{score_text}</b></td></tr>')
            st.html(f'<table class="history-table" style="--history-rows:{len(visible)}"><thead><tr><th>序号</th><th>检测图片</th><th>缺陷类型</th><th>评分</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table>')
            previous, status, following = st.columns([1, 1.4, 1])
            with previous:
                if st.button('上一页', disabled=page <= 1, key='history_previous'):
                    st.session_state['history_page'] = page - 1
                    st.rerun(scope='fragment')
            with status:
                st.html(f'<div class="history-page">{page} / {pages} 页 · 共 {len(records)} 次</div>')
            with following:
                if st.button('下一页', disabled=page >= pages, key='history_next'):
                    st.session_state['history_page'] = page + 1
                    st.rerun(scope='fragment')
    with right, st.container(key='history-growth'):
        st.subheader('分数成长曲线')
        scored = [record for record in records if record['score'] is not None]
        if not scored:
            st.html('<div class="trend-chart-empty">等待首个有效评分</div>')
            st.html(summary_html(records))
            return
        first, latest = scored[0]['score'], scored[-1]['score']
        change = latest - first
        st.html(f'<div class="history-stats"><span>最新 <b>{latest}</b></span><span>最高 <b>{max(r["score"] for r in scored)}</b></span><span>较首次 <b>{change:+d}</b></span></div>')
        recent = scored[-30:]
        data = pd.DataFrame([{'次序': index + 1, '评分': record['score'], '记录序号': record['sequence'],
                              '时间': display_time(record['generated_at'])} for index, record in enumerate(scored) if record in recent])
        chart = alt.Chart(data).mark_line(color='#0d9488', strokeWidth=4, point=alt.OverlayMarkDef(size=120, filled=True)).encode(
            x=alt.X('次序:Q', title='有效评分次数', axis=alt.Axis(tickMinStep=1, tickCount=min(5, len(recent))),
                    scale=alt.Scale(domain=[max(0, len(scored)-len(recent)), len(scored)+1])),
            y=alt.Y('评分:Q', title='分数', scale=alt.Scale(domain=[0, 100]), axis=alt.Axis(values=[0, 20, 40, 60, 80, 100])),
            tooltip=['记录序号:Q', '时间:N', '评分:Q'],
        ).properties(height=240).configure_axis(labelFontSize=20, titleFontSize=22, titlePadding=10, labelColor='#334155', titleColor='#334155').configure_view(stroke=None)
        st.altair_chart(chart, width='stretch', key='history_score_chart')
        st.html(summary_html(records))
