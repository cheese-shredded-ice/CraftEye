"""Evidence-based summaries of local practice records; no extra API request."""
from collections import Counter
from html import escape
import re
from statistics import mean

PRACTICE_TIPS = {
    '气孔': '先清理焊前表面，练完检查小孔是否减少。',
    '夹渣': '先做好层间清理，再请老师检查结合情况。',
    '裂纹': '先请老师复查裂口，再按指导调整练习。',
    '未焊透': '请老师检查根部与装配，再做针对性练习。',
    '未熔合': '请老师检查结合位置，再练习稳定运条。',
    '咬边': '先练匀速走枪，练完检查两侧凹槽。',
    '焊瘤': '先练匀速走枪，比较边缘堆搭是否减少。',
    '烧穿': '按老师给定参数试焊，检查是否仍有贯穿孔。',
    '弧坑': '重点练习收弧填坑，观察末端是否饱满。',
    '飞溅过多': '请老师核对工艺参数，试焊后比较飞溅。',
    '焊缝成形不良': '练习匀速走枪，比较前中后段宽窄。',
}


def training_summary(records):
    scored = [record['score'] for record in records if type(record.get('score')) is int and 0 <= record['score'] <= 100]
    if not scored:
        trend = '暂无有效评分，完成练习后查看变化。'
    elif len(scored) < 3:
        trend = f'已有 {len(scored)} 次评分，暂不足以判断趋势。'
    elif len(scored) < 6:
        trend = f'近 {len(scored)} 次均分 {mean(scored):.1f}，范围 {min(scored)}–{max(scored)} 分。'
    else:
        previous, recent = mean(scored[-6:-3]), mean(scored[-3:])
        delta = recent - previous
        direction = f'上升 {delta:.1f}' if delta >= 2 else f'下降 {abs(delta):.1f}' if delta <= -2 else '基本持平'
        trend = f'近3次均分 {recent:.1f}，较前3次{direction}' + ('。' if abs(delta) < 2 else ' 分。')
    window = records[-5:]
    counts = Counter()
    for record in window:
        names = set()
        for item in record.get('defects', []):
            match = re.match(r'^(?:疑似\s*)?([^：:]+)[：:]', item.strip())
            if match:
                name = match.group(1).strip()
                name = {'焊接成形不良': '焊缝成形不良'}.get(name, name)
                if name in PRACTICE_TIPS:
                    names.add(name)
        counts.update(sorted(names))
    if counts:
        top = sorted(counts, key=lambda name: (-counts[name], name))[:2]
        defects = f'近{len(window)}次：' + '、'.join(f'疑似{name} {counts[name]}次' for name in top) + '。'
        practice = PRACTICE_TIPS[top[0]]
    else:
        defects = '近期暂无明确的疑似类型记录。' if records else '尚无缺陷记录。'
        practice = '保持同一练习目标，记录下一次结果再比较。'
    return {'分数变化': trend, '关注缺陷': defects, '下次重点': practice}


def summary_html(records):
    rows = ''.join(f'<div class="trend-row"><strong>{title}</strong><p>{escape(text)}</p></div>'
                   for title, text in training_summary(records).items())
    return '<section class="training-trend" aria-label="训练趋势总结"><h4>训练趋势总结</h4>' + rows + '</section>'
