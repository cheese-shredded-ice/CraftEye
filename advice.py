"""Conditional troubleshooting guidance; model labels do not diagnose parameters."""

OBSERVATIONS = {
    '烧穿、熔池过大或边缘塌陷': {
        '排查方向': '电流偏大 / 行走速度偏慢',
        '可能原因': '热输入偏高；板厚、接头间隙或局部散热条件也可能影响成形。',
        '调整建议': '核对板厚、间隙和焊接工艺规程允许的参数范围。确认热输入偏高后，试焊时逐项检查降低电流或提高行走速度的效果。',
    },
    '焊缝窄、填充不足或焊道不连续': {
        '排查方向': '行走速度偏快 / 填充量不足',
        '可能原因': '行走过快、填充或送丝不足；电流偏低也可能伴随熔合不足。',
        '调整建议': '先核实填充量和实际行走速度，再在工艺规程范围内试调速度或送丝参数；结合接头检查熔合情况，不能仅按图片提高电流。',
    },
    '焊缝堆高、焊道过宽或局部堆积': {
        '排查方向': '行走速度偏慢 / 填充量偏大',
        '可能原因': '行走或停留过慢、填充量偏大；焊道宽度还受电压、摆动和接头形式影响。',
        '调整建议': '核对焊道尺寸要求，检查行走是否均匀、是否停留过久；在规定范围内逐项试调行走速度、填充量或摆动幅度。',
    },
    '焊缝偏向一侧或两侧成形不一致': {
        '排查方向': '焊枪角度或指向不合适',
        '可能原因': '工作角、行走角或焊枪指向偏离接头；装配偏差和两侧散热差异也可能造成不对称。',
        '调整建议': '检查焊枪是否对准接头、两侧停留是否一致，并按当前焊接方法、位置和接头要求校正角度；不能统一套用固定角度。',
    },
    '焊趾衔接差或疑似未熔合': {
        '排查方向': '电流偏小 / 速度偏快 / 焊枪角度不合适',
        '可能原因': '有效热输入不足、焊枪未对准待熔合位置或表面氧化物未清理。',
        '调整建议': '先清理表面并核对焊枪指向，再按工艺规程检查电流和速度；需要通过适用的检验方法确认熔合，外观图无法确认内部缺陷。',
    },
    '飞溅明显、表面有孔洞或气体保护异常': {
        '排查方向': '参数匹配 / 表面清洁 / 气体保护（适用时）',
        '可能原因': '电流电压或送丝配合不当、弧长不稳定、表面污染；使用保护气体时还需排查气路和风扰。',
        '调整建议': '检查材料清洁度、焊材状态及电流电压或送丝匹配；有保护气体时按工艺要求检查流量、漏气和喷嘴。不要仅凭飞溅判定电流过大。',
    },
}

LIMITATION = '模型只识别“焊接不良、焊接良好、缺陷”，不测量电流、焊枪角度或速度。以下是条件式排查建议，不是已确认的故障原因；检测置信度不代表原因判断的可信度。'
METHOD = '调整前核对焊接方法、材料、板厚、接头形式和焊接工艺规程（WPS）；在允许范围内一次只调整一个因素，试焊后复检。'


def build_advice(class_ids, observations=()):
    detected = set(class_ids)
    selected = [name for name in OBSERVATIONS if name in observations]
    abnormal = bool(detected & {0, 2})
    if abnormal:
        summary = '检测到焊接不良或缺陷区域，建议对照实际现象排查工艺参数。'
    elif selected:
        summary = '模型未报告不良或缺陷，但你补充了异常现象；请优先核实这些现场现象。'
    elif 1 in detected:
        summary = '当前检出区域被标记为焊接良好，暂不建议仅凭图片改变电流、角度或速度；仍需按工艺要求复核。'
    else:
        summary = '当前阈值下未检出目标，无法据此判断合格或推荐参数调整。请补拍清晰的焊缝近照后再识别。'
    # Manual observations narrow the list; generic model labels never select a cause.
    conditions = selected if selected else list(OBSERVATIONS) if abnormal else []
    items = [{'需核实的现象': condition, **OBSERVATIONS[condition]} for condition in conditions]
    return {
        'summary': summary,
        'basis': '按你人工选择的现象提供建议' if selected else '按模型粗类别提供通用排查清单',
        'manual_observations': selected,
        'limitation': LIMITATION,
        'recommendations': items,
        'method': METHOD if items else '如现场存在异常，可补充实际现象后查看对应排查建议。',
    }


def advice_text(advice):
    lines = ['焊接检测建议', advice['summary'], advice['basis'], advice['limitation'], '']
    for item in advice['recommendations']:
        lines.extend([f"需核实的现象：{item['需核实的现象']}",
                      f"排查方向：{item['排查方向']}",
                      f"可能原因：{item['可能原因']}",
                      f"调整建议：{item['调整建议']}", ''])
    lines.append(advice['method'])
    return '\n'.join(lines)
