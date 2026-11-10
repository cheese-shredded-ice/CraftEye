"""Five-band score scale; values are derived from the fixed weighted rubric."""
from html import escape
from dashboard_visuals import svg_url


from scoring import PROGRESS_BANDS, progress_band, scale_position


def score_html(score):
    value = score['分数']
    color, label = progress_band(value)
    position = scale_position(value)
    number = '—' if value is None else str(value)
    accessible = '暂无法评分' if value is None else f'本次评分 {value} 分，满分 100 分，{label}'
    marker = '' if value is None else f'<span class="score-marker" style="left:{position}%;background:{color}"></span>'
    labels = ''.join(f'<span class="score-grade" title="分数档位">'
                     f'{grade}<small>（{lower}–{upper}）</small></span>'
                     for lower, upper, grade, _ in PROGRESS_BANDS)
    def number_text(key):
        return '—' if score.get(key) is None else str(score[key])
    deduction = number_text('短板惩罚')
    if score.get('短板惩罚'):
        deduction = '−' + deduction
    breakdown = ('<div class="score-breakdown">'
                 f'<span>基础分 <b>{number_text("基础分")}</b></span>'
                 f'<span>短板惩罚 <b>{deduction}</b></span>'
                 f'<span>最终分 <b>{number}</b></span></div>')
    cap_note = ''
    if score.get('关键缺陷'):
        types = '、'.join(item['类型'] for item in score['关键缺陷'])
        amount = score.get('关键缺陷扣分')
        deduction_text = '' if amount is None else f' · 另扣{amount}分'
        cap_note = f'<div class="score-cap-note">{escape(types)}风险：不符合 · 最高{score["分数上限"]}分{deduction_text}</div>'
    meter = (f'role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{value}" '
             f'aria-valuetext="{value}分，{label}"') if value is not None else 'role="img"'
    progress = 0 if value is None else value
    gauge = svg_url(f'<defs><linearGradient id="g"><stop stop-color="{color}"/><stop offset="1" stop-color="{color}" stop-opacity="0.65"/></linearGradient></defs>'
                    f'<path d="M 30 162 A 90 90 0 1 1 210 162" stroke="#deedf8" stroke-width="16" pathLength="100"/>'
                    f'<path d="M 30 162 A 90 90 0 1 1 210 162" stroke="url(#g)" stroke-width="16" pathLength="100" stroke-dasharray="{progress} 100"/>', '0 0 240 200')
    score_caption = '可见项参考分 / 100' if score.get('评分类型') == '可见项参考分' else '最终分 / 100'
    return f'''<div class="score-summary" data-weld-score="{number}">
<div class="score-gauge" aria-label="{accessible}"><img src="{gauge}" alt="" aria-hidden="true">
<div class="gauge-value"><div><strong style="color:{color}">{number}</strong><b style="color:{color}">分</b></div><small>{score_caption}</small></div></div>
<div class="score-detail"><div class="score-scale{" unscored" if value is None else ""}" data-score-progress="{number}" {meter} aria-label="{accessible}">
<div class="score-status-row"><span class="score-status" style="background:{color};left:clamp(60px,{position}%,calc(100% - 60px))">{label}</span></div>
<div class="score-track">{marker}</div><div class="score-grades">{labels}</div></div>
{breakdown}{cap_note}</div></div>'''
