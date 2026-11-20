"""Paginated history table and score trend for the presentation workspace."""
import csv
import base64
from datetime import datetime
from html import escape
import io
import json
import zipfile

import streamlit as st

from .recognition_history import load_records, load_original_images, load_record_detail, delete_records
from .teaching_report_ui import dimensions_html
from .score_ui import score_html
from .training_trends import summary_html
from .scoring import decision_style
from .analysis_audit import audit_html
from .growth_chart import growth_chart
from .demo_history import ensure_training_records

PAGE_SIZE = 5


def delete_history_record(run_id):
    """Delete the clicked record by stable ID, even if pagination changes."""
    try:
        count = delete_records([run_id])
    except Exception:
        st.session_state['_history_row_error'] = '删除失败，请重试。'
    else:
        st.session_state['_history_delete_reset'] = True
        # Fragment callbacks must not emit UI: Streamlit can replace elements
        # at the top of the page with callback output during its next rerun.
        st.session_state['_history_row_notice'] = '已删除该记录' if count else '该记录已删除'


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
    writer.writerow(['序号', '识别时间', '来源', '分数', '缺陷类型', '评分理由', '改良建议', '评分类型',
                     '基础分', '短板惩罚', '最终分', '等级', '是否达到教学目标', '判定依据', '评分版本',
                     '限分前得分', '关键缺陷扣分', '关键缺陷依据'])
    for record in records:
        values = [record['display_sequence'], record['generated_at'], {'camera':'摄像头','training':'训练图片'}.get(record['source_type'], '摄像头' if record['source_type'] == 'camera' else '图片'),
                  record['score'] if record['score'] is not None else '暂无法评分',
                  '；'.join(record['defects']), record['reason'], record['suggestion'], record.get('score_type') or '历史评分']
        assessment = record.get('assessment') or {}
        values.extend(assessment.get(key, '') for key in ('基础分', '短板惩罚', '最终分', '等级', '是否达到教学目标'))
        values.extend(['；'.join(assessment.get('判定依据', [])), record.get('rubric_version') or '历史规则'])
        values.extend([assessment.get('限分前得分', ''), assessment.get('关键缺陷扣分', ''),
                       '；'.join(item['类型'] + '：' + item['依据'] for item in assessment.get('关键缺陷', []))])
        writer.writerow(["'" + value if isinstance(value, str) and value.startswith(('=', '+', '-', '@')) else value for value in values])
    return output.getvalue().encode('utf-8-sig')


def close_history_dialog():
    st.session_state['_history_delete_open'] = False


def close_history_detail():
    st.session_state.pop('_history_detail_id', None)


def detail_archive(detail):
    """One self-contained download: frozen report, inputs and both image variants."""
    output = io.BytesIO()
    payload = {key: value for key, value in detail.items() if key not in {'original_png', 'annotated_png'}}
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('report.json', json.dumps(payload, ensure_ascii=False, indent=2))
        for field, name in [('original_png', 'original.png'), ('annotated_png', 'detection.png')]:
            if detail.get(field):
                archive.writestr(name, detail[field])
    return output.getvalue()


@st.dialog('识别记录详情', width='large', on_dismiss=close_history_detail)
def history_detail_dialog(run_id):
    detail = load_record_detail(run_id)
    if detail is None:
        st.info('该记录已删除。')
        return
    report, inputs = detail['analysis'], detail['inputs']
    st.subheader(f'第 {detail["display_sequence"]} 次识别')
    source_label = {'camera': '摄像头', 'training': '训练图片'}.get(inputs.get('source_type'), '图片')
    caption = ' · '.join(part for part in (report.get('generated_at'), source_label) if part)
    st.caption(caption)
    st.download_button('下载本次完整记录', detail_archive(detail),
                       f'识别记录-{detail["display_sequence"]}.zip', 'application/zip', on_click='ignore')
    if st.button('关闭详情', key='history_detail_close'):
        close_history_detail()
        st.rerun()
    if not detail['complete_snapshot']:
        st.info('旧版本未保存完整报告，以下仅显示当时已保存的内容。')
    with st.container(key='history-detail-images'):
        left, right = st.columns(2)
        with left:
            st.markdown('**原始图片**')
            if detail['original_png']:
                st.image(detail['original_png'], width='stretch')
            else:
                st.info('此记录未保存原图。')
        with right:
            st.markdown('**检测结果**')
            if detail['annotated_png']:
                st.image(detail['annotated_png'], width='stretch')
            else:
                st.info('此记录未保存检测图。')
    with st.container(key='history-detail-score'):
        st.html(score_html(report['score']))
    with st.container(key='history-detail-audit'):
        from PIL import Image
        original = Image.open(io.BytesIO(detail['original_png'])).convert('RGB') if detail['original_png'] else None
        st.html(audit_html(report, original, inputs))
    if report.get('learning_goal'):
        st.write('训练目标：' + report['learning_goal'])
    st.write('评分理由：' + report['score'].get('理由', '未保存'))
    if report.get('dimensions'):
        with st.container(key='history-detail-dimensions'):
            st.html(dimensions_html(report['dimensions']))
    for name in ['缺陷类型', '图中现象', '可能原因', '改良建议']:
        st.markdown('**【' + name + '】**')
        values = report.get('sections', {}).get(name)
        if values:
            for value in values:
                st.write(value)
        else:
            st.caption('旧记录未保存此项。')
    with st.expander('检测数据与评分依据'):
        if inputs.get('detections'):
            st.dataframe(inputs['detections'], hide_index=True, width='stretch')
        elif 'detections' in inputs:
            st.write('本次未检出目标。')
        else:
            st.write('旧记录未保存检测框数据。')
        st.json({'评分': report['score'], '输入': inputs,
                 '模型': report.get('model'), '评分版本': report.get('rubric_version'),
                 '分析版本': report.get('feedback_version'), '重点区域': report.get('focus_regions', [])})


@st.dialog('删除识别记录', on_dismiss=close_history_dialog)
def delete_history_dialog():
    records = [record for record in load_records() if record.get('source_type') != 'training']
    lookup = {record['run_id']: record for record in records}
    def record_label(run_id):
        record = lookup.get(run_id)
        if record is None:
            return '记录已删除'
        score = '暂无评分' if record['score'] is None else f'{record["score"]}分'
        return f'第{record["display_sequence"]}次 · {display_time(record["generated_at"])} · {score}'
    selected = st.multiselect('选择要删除的记录', list(reversed(lookup)), format_func=record_label,
                              key='history_delete_selection', placeholder='按序号选择，可多选')
    st.caption('删除后，对应检测图片也会移除。')
    if st.button('删除所选记录', key='history_delete_confirm', disabled=not selected, type='primary'):
        try:
            count = delete_records(selected)
        except Exception:
            st.error('删除失败，记录已保留，请重试。')
        else:
            st.session_state['_history_delete_reset'] = True
            close_history_dialog()
            st.toast(f'已删除 {count} 条记录')
            st.rerun()


def render_history():
    try:
        ensure_training_records()
    except Exception:
        st.error('训练记录暂时无法载入，请检查本地存储。')
        return
    # Pause history polling while a dialog is open so it cannot dismiss the form.
    opened = st.session_state.get('_history_delete_open', False)
    detail_id = st.session_state.get('_history_detail_id')
    st.fragment(run_every=None if opened or detail_id else 2.0)(_render_history)()
    if opened:
        delete_history_dialog()
    elif detail_id:
        history_detail_dialog(detail_id)


def _render_history():
    left, right = st.columns([1.1, 1.2], gap='medium')
    growth = right.container(key='history-growth')
    growth.subheader('训练成长曲线')
    page_key = 'history_page'
    try:
        records = load_records()
    except Exception:
        st.error('识别记录暂时无法读取，请检查本地存储。')
        return
    if st.session_state.pop('_history_delete_reset', False):
        st.session_state.pop('history_delete_selection', None)
    if message := st.session_state.pop('_history_row_notice', None):
        st.toast(message)
    with left, st.container(key='history-table'):
        title, download, remove = st.columns([1.55, 1, .75])
        editable_records = [record for record in records if record.get('source_type') != 'training']
        with title:
            st.subheader('识别记录表')
        with download:
            st.download_button('导出记录', export_csv(records), '识别记录.csv', 'text/csv', disabled=not records, on_click='ignore')
        with remove:
            if st.button('删除', key='history_bulk_delete', disabled=not editable_records, use_container_width=True):
                st.session_state['_history_delete_open'] = True
                st.rerun()
        if message := st.session_state.pop('_history_row_error', None):
            st.error(message)
        if not records:
            st.html('<div class="history-empty">暂无记录<br>完成一次综合分析后自动保存</div>')
        else:
            pages = (len(records) + PAGE_SIZE - 1) // PAGE_SIZE
            page = min(st.session_state.get(page_key, 1), pages)
            st.session_state[page_key] = page
            visible = list(reversed(records))[(page-1)*PAGE_SIZE:page*PAGE_SIZE]
            images = load_original_images([record['run_id'] for record in visible])
            with st.container(key='history-record-grid'):
                st.html(f'<style>.st-key-history-record-grid{{--history-count:{len(visible)};}}</style>'
                        '<div class="history-record-header"><div class="history-record-cells">'
                        '<b>序号</b><b>图片</b><b>缺陷类型</b><b>评分</b></div><b>操作</b></div>')
                with st.container(key='history-record-list'):
                    for record in visible:
                        score = record['score']
                        color, label = decision_style(record.get('assessment') or {})
                        score_text = '—' if score is None else str(score)
                        image_data = images.get(record['run_id'])
                        picture = (f'<img class="history-original-thumbnail" src="data:image/png;base64,{base64.b64encode(image_data).decode("ascii")}" alt="第{record["display_sequence"]}次图片">'
                                   if image_data else '<span class="history-no-image">未保存原图</span>')
                        defects = escape(defect_label(record['defects']))
                        with st.container(key='history-entry-'+record['run_id']):
                            cells, actions = st.columns([.82, .18], gap='small', vertical_alignment='center')
                            with cells:
                                st.html(f'<div class="history-record-cells" data-record-id="{escape(record["run_id"], quote=True)}">'
                                        f'<span title="{escape(record["generated_at"], quote=True)}">{record["display_sequence"]}</span>'
                                        f'<div>{picture}</div><span class="history-defect-text" title="{defects}">{defects}</span>'
                                        f'<span class="history-record-score" style="color:{color}"><b>{score_text}</b><small>{label}</small></span></div>')
                            with actions, st.container(key='history-actions-'+record['run_id']):
                                if st.button('详情', key=f'history_row_detail_{record["run_id"]}', use_container_width=True):
                                    st.session_state['_history_detail_id'] = record['run_id']
                                    st.rerun()
                                if record.get('source_type') != 'training':
                                    st.button('删除', key=f'history_row_delete_{record["run_id"]}',
                                              on_click=delete_history_record, args=(record['run_id'],), use_container_width=True)
            previous, status, following = st.columns([1, 1.4, 1])
            with previous:
                if st.button('上一页', disabled=page <= 1, key='history_previous'):
                    st.session_state[page_key] = page - 1
                    st.rerun(scope='fragment')
            with status:
                st.html(f'<div class="history-page">{page} / {pages} 页 · 共 {len(records)} 次</div>')
            with following:
                if st.button('下一页', disabled=page >= pages, key='history_next'):
                    st.session_state[page_key] = page + 1
                    st.rerun(scope='fragment')
    with growth:
        scored = [record for record in records if record['score'] is not None]
        if not records:
            st.html('<div class="trend-chart-empty">等待首个有效评分</div>')
            st.html(summary_html(records))
            return
        first, latest = (scored[0]['score'], scored[-1]['score']) if scored else (None, None)
        change = f'{latest-first:+d}' if scored else '—'
        st.html(f'<div class="history-stats"><span>最近有效 <b>{latest if scored else "—"}</b></span><span>最高 <b>{max(r["score"] for r in scored) if scored else "—"}</b></span><span>较首次 <b>{change}</b></span></div>')
        missing = '<span>× 未评分</span>' if len(scored) < len(records) else ''
        st.html(f'<div class="growth-legend"><span>● 综合评分</span>{missing}</div>')
        chart = growth_chart(records)
        st.altair_chart(chart, width='stretch', height='stretch', key='history_score_chart')
        st.html(f'<div class="growth-caption">{len(records)} 条记录逐一对应 · {len(scored)} 次有效评分 · 横轴为记录序号</div>')
        st.html(summary_html(records))
