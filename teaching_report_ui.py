"""Compact report with locally embedded reference images and escaped AI text."""
import base64
from functools import lru_cache
from html import escape
import io
import math

from ai_analysis import SECTIONS
from defect_references import REFERENCES, REFERENCE_DIR, matched_references
from score_ui import score_html
from scoring import DIMENSIONS, SCORE_FORMULA, score_band
from dashboard_visuals import icon_html


def dimensions_html(dimensions=None, formula=None):
    """Six-axis radar; unknown axes never become zero-valued vertices."""
    cx, cy, radius = 400, 185, 112
    def point(index, value=100):
        angle = math.radians(-90 + index * 60)
        return cx + radius * value / 100 * math.cos(angle), cy + radius * value / 100 * math.sin(angle)
    def coordinates(points):
        return ' '.join(f'{x:.2f},{y:.2f}' for x, y in points)
    parts = ['<svg viewBox="140 -30 520 400" role="img" aria-label="六维评分雷达图" xmlns="http://www.w3.org/2000/svg">',
             '<title>六维评分：中心0分，外圈100分</title>']
    for level in (20, 40, 60, 80, 100):
        points = coordinates([point(index, level) for index in range(6)])
        parts.append(f'<polygon points="{points}" fill="none" stroke="#cbd5e1" stroke-width="1.5"/>')
    for index in range(6):
        x, y = point(index)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.2f}" y2="{y:.2f}" stroke="#94a3b8" stroke-width="1.5"/>')
    values = [(dimensions or {}).get(name, {}).get('分数') for name, _ in DIMENSIONS]
    if all(value is not None for value in values):
        points = coordinates([point(index, value) for index, value in enumerate(values)])
        parts.append(f'<polygon class="radar-area" points="{points}" fill="#c084fc" fill-opacity="0.4" stroke="#9333ea" stroke-width="3.5"/>')
    else:
        for index, value in enumerate(values):
            other = (index + 1) % 6
            if value is not None and values[other] is not None:
                points = coordinates([point(index, value), point(other, values[other])])
                parts.append(f'<polyline points="{points}" fill="none" stroke="#9333ea" stroke-width="3.5"/>')
    labels = [(400, -3, 'middle'), (535, 108, 'start'), (535, 260, 'start'),
              (400, 330, 'middle'), (265, 260, 'end'), (265, 108, 'end')]
    for index, ((name, weight), (x, y, anchor)) in enumerate(zip(DIMENSIONS, labels)):
        item = (dimensions or {}).get(name)
        value = values[index]
        number = '—' if item and value is None else ('待识别' if value is None else f'{value}分')
        if item and value is not None and '得分' in item:
            number = f'{item["得分"]}/{item["满分"]}分'
        color, _ = score_band(value)
        reason = item['理由'] if item else '等待识别'
        label = (f'<tspan x="{x}" dy="-24">焊道走向</tspan><tspan x="{x}" dy="24">稳定性</tspan>'
                 if name == '焊道走向稳定性' else name)
        parts.append(f'<g class="radar-dimension"><title>{escape(name)}：{number}；{escape(reason)}</title>'
                     f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="#164e49" font-size="24" font-weight="700">{label}</text>'
                     f'<text x="{x}" y="{y+25}" text-anchor="{anchor}" font-size="22">'
                     f'<tspan fill="{color}" font-weight="700">{number}</tspan></text></g>')
        if value is not None:
            px, py = point(index, value)
            parts.append(f'<circle class="radar-point" cx="{px:.2f}" cy="{py:.2f}" r="5" fill="{color}" stroke="white" stroke-width="2">'
                         f'<title>{escape(name)}：{value}分；{escape(reason)}</title></circle>')
    parts.append('</svg>')
    # Streamlit's HTML sanitizer removes inline SVG; an image source preserves it.
    source = base64.b64encode(''.join(parts).encode('utf-8')).decode('ascii')
    reviews = ''.join(
        '<div class="dimension-review"><p>'
        f'<strong>{escape(name)}：</strong>'
        f'{escape((dimensions or {}).get(name, {}).get("理由", "等待识别"))}'
        '</p></div>' for name, _ in DIMENSIONS)
    description = '；'.join(f'{name}：{value if value is not None else "—"}，权重{weight}%'
                           for (name, weight), value in zip(DIMENSIONS, values))
    formula_html = f'<div class="dimension-formula">{escape(formula)}</div>' if formula else ''
    return ('<div class="dimension-layout"><div class="dimension-radar">'
            f'<img class="radar-image" aria-label="六维评分雷达图" alt="{escape(description, quote=True)}" '
            f'src="data:image/svg+xml;base64,{source}">{formula_html}</div>'
            f'<div class="dimension-reviews" aria-label="各维度评价">{reviews}</div></div>')


@lru_cache(maxsize=9)
def reference_url(filename):
    return 'data:image/jpeg;base64,' + base64.b64encode((REFERENCE_DIR / filename).read_bytes()).decode('ascii')


def original_url(original):
    image = original.convert('RGB').copy()
    image.thumbnail((640, 480))
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def report_html(report, original, view='改进建议'):
    sections = report['sections']
    length = sum(len(item) for items in sections.values() for item in items)
    density = ' dense' if length > 150 or len(sections.get('缺陷类型', [])) > 2 else ''
    parts = [f'<div class="teaching-report{density}">', score_html(report['score'])]
    if view == '六维评分':
        formula = (SCORE_FORMULA if report['score']['分数'] is not None
                   else '可评项目不足，暂不计算总分')
        if report['score'].get('评分类型') == '可见项参考分':
            formula = f'可见项参考分 · {report["score"]["可评维度数"]}/6项 · 覆盖{report["score"]["可评权重"]}%'
        if report['score'].get('关键缺陷'):
            formula = '关键缺陷限分 · 最终分最高59分'
        parts.append('<div class="radar-card">' + dimensions_html(report.get('dimensions'), formula) + '</div></div>')
        return ''.join(parts)
    names = matched_references(sections['缺陷类型'])[:2]
    parts.append('<div class="analysis-content"><div class="feedback-card">')
    icons = {'缺陷类型': 'target', '图中现象': 'image', '可能原因': 'question', '改良建议': 'bulb'}
    for section in SECTIONS:
        text = ''.join(f'<p>{escape(item)}</p>' for item in sections[section])
        parts.append(f'<div class="feedback-row"><div class="feedback-title">{icon_html(icons[section])}<span>【{section}】</span></div><div class="feedback-text">{text}</div></div>')
    parts.append('</div>')
    parts.append(f'<div class="reference-grid" aria-label="缺陷对比图" style="--reference-count:{len(names)+1}">'
                 f'<figure><img src="{original_url(original)}" alt="本次识别图片原图"><figcaption>本次识别图片</figcaption></figure>')
    for name in names:
        filename, _ = REFERENCES[name]
        parts.append(f'<figure><img src="{reference_url(filename)}" alt="{name}典型示例"><figcaption>{name} · 典型示例</figcaption></figure>')
    parts.append('</div></div></div>')
    return ''.join(parts)
