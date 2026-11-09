"""Compact report with locally embedded reference images and escaped AI text."""
import base64
from functools import lru_cache
from html import escape
import io

from ai_analysis import SECTIONS
from defect_references import REFERENCES, REFERENCE_DIR, matched_references
from score_ui import score_html


@lru_cache(maxsize=9)
def reference_url(filename):
    return 'data:image/jpeg;base64,' + base64.b64encode((REFERENCE_DIR / filename).read_bytes()).decode('ascii')


def original_url(original):
    image = original.convert('RGB').copy()
    image.thumbnail((640, 480))
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG', quality=85)
    return 'data:image/jpeg;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')


def report_html(report, original):
    sections = report['sections']
    length = sum(len(item) for items in sections.values() for item in items)
    density = ' dense' if length > 150 else ''
    parts = [f'<div class="teaching-report{density}">', score_html(report['score'])]
    for section in SECTIONS:
        text = ''.join(f'<p>{escape(item)}</p>' for item in sections[section])
        parts.append(f'<div class="feedback-row"><div class="feedback-title">【{section}】</div><div class="feedback-text">{text}</div></div>')
        if section == '缺陷类型':
            names = matched_references(sections[section])
            if names:
                parts.append(f'<div class="reference-grid" aria-label="缺陷对比图" style="--reference-count:{len(names)+1}">'
                             f'<figure><img src="{original_url(original)}" alt="本次识别图片原图"><figcaption>本次识别图片</figcaption></figure>')
                for name in names:
                    filename, _ = REFERENCES[name]
                    parts.append(f'<figure><img src="{reference_url(filename)}" alt="{name}典型示例"><figcaption>{name} · 典型示例</figcaption>'
                                 '</figure>')
                parts.append('</div>')
    parts.append('</div>')
    return ''.join(parts)
