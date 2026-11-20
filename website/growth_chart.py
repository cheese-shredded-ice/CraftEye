"""Honest score progression: one identity per record, gaps and declines preserved."""
import altair as alt


def growth_data(records):
    rows, best, segment, previous_version, rule_stage = [], None, 0, None, 0
    for record in records:
        value = record.get('score')
        version = record.get('rubric_version') or '历史规则'
        if previous_version is not None and previous_version != version:
            segment += 1
            rule_stage += 1
            best = None
        if value is None:
            segment += 1
        if value is not None:
            best = value if best is None else max(best, value)
        rows.append({'记录序号':record.get('display_sequence', record['sequence']), '记录ID':record['run_id'], '时间':record['generated_at'],
                     '评分':value, '历次最高':best, '状态':'未评分' if value is None else '已评分',
                     '评分规则':version, '规则阶段':str(rule_stage), '线段':str(segment), '缺项标记':-8 if value is None else None})
        previous_version = version
    return rows


def growth_chart(records):
    data = growth_data(records)
    points = alt.Data(values=[row for row in data if row['评分'] is not None])
    sequences = [row['记录序号'] for row in data] or [1]
    axis_fonts = {'labelFontSize': alt.ExprRef(expr='width < 450 ? 12 : width < 700 ? 14 : 18'),
                  'titleFontSize': alt.ExprRef(expr='width < 450 ? 14 : width < 700 ? 16 : 20')}
    x = alt.X('记录序号:Q', title='训练 / 识别次数 →', scale=alt.Scale(domain=[min(sequences)-.4, max(sequences)+.4]),
              axis=alt.Axis(tickMinStep=1, tickCount=min(6,len(data)), **axis_fonts))
    y_axis = alt.Axis(values=[0,20,40,60,80,100],labelOverlap=False, **axis_fonts)
    y = alt.Y('评分:Q', title='分数 ↑', scale=alt.Scale(domain=[-12,100]), axis=y_axis)
    identity = ['记录序号:Q','时间:N']
    tooltip = identity + ['评分:Q','状态:N','评分规则:N','记录ID:N']
    base = alt.Chart(points).encode(x=x,y=y,tooltip=tooltip)
    line = base.mark_line(color='#0d9488', strokeWidth=3).encode(detail='线段:N',order='记录序号:Q')
    dots = base.mark_point(color='#0070a9', size=85,filled=True)
    missing = alt.Chart(alt.Data(values=[row for row in data if row['评分'] is None])).mark_point(shape='cross',color='#94a3b8',size=80).encode(
        x=x,y=alt.Y('缺项标记:Q',title='分数 ↑',scale=alt.Scale(domain=[-12,100]),axis=y_axis),tooltip=identity+['状态:N','记录ID:N'])
    return (line+dots+missing).properties(height='container').configure_axis(
        titlePadding=4,labelColor='#334155',titleColor='#334155').configure_view(stroke=None)
