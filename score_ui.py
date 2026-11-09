"""Accessible score ring; the numeric value is validated by the AI parser."""
from html import escape


def score_band(value):
    if value is None:
        return '#64748b', '暂无法评分'
    if value < 60:
        return '#dc2626', '重点练习'
    if value < 80:
        return '#b45309', '继续巩固'
    return '#15803d', '保持并提升'


def score_html(score):
    value = score['分数']
    color, label = score_band(value)
    number = '—' if value is None else str(value)
    progress = 0 if value is None else value
    accessible = '暂无法评分' if value is None else f'本次评分 {value} 分，满分 100 分，{label}'
    return f'''<div data-weld-score="{number}" style="display:flex;align-items:center;gap:22px;flex-wrap:wrap;padding:12px 0 18px">
<div role="img" aria-label="{accessible}" data-score-ring="{progress}" style="width:108px;height:108px;flex-shrink:0;border-radius:50%;background:conic-gradient({color} 0% {progress}%,#e2e8f0 {progress}% 100%);mask:radial-gradient(farthest-side,transparent calc(100% - 10px),#000 calc(100% - 9px))"></div>
<div style="flex:1;min-width:190px"><div class="score-line"><span class="score-label">【本次评分】</span> <strong style="font-size:36px;color:{color}">{number}</strong>
<span style="font-size:16px"> / 100 分</span><span style="margin-left:16px;color:{color};font-weight:600">{label}</span></div>
<div style="margin-top:5px">{escape(score['理由'])}</div></div></div>'''
