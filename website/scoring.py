"""Unified six-axis appearance teaching score with a weakest-axis penalty."""
from fractions import Fraction
import re
DIMENSIONS = (
    ('成形质量', 20),
    ('焊道连续性', 20),
    ('焊趾过渡', 15),
    ('表面质量', 20),
    ('焊道走向稳定性', 15),
    ('焊后清洁度', 10),
)
RUBRIC_VERSION = 'welding-v9-critical-cap-v1'
CRITICAL_SCORE_CAP = 59
MIN_VISIBLE_DIMENSIONS = 4
MIN_VISIBLE_WEIGHT = 60
BASE_PERCENT = 80
MINIMUM_PERCENT = 20
PASS_SCORE, PASS_MINIMUM = 85, 70
EXCELLENT_SCORE, EXCELLENT_MINIMUM = 93, 85
SCORE_FORMULA = f'最终分 = {BASE_PERCENT}%基础分 + {MINIMUM_PERCENT}%最低项'
SCORE_BANDS = ((0, 59, '严重不符合', '#dc2626'), (60, 74, '不符合', '#c2410c'),
               (75, PASS_SCORE - 1, '需改进', '#a16207'), (PASS_SCORE, EXCELLENT_SCORE - 1, '符合', '#0f766e'),
               (EXCELLENT_SCORE, 100, '非常符合', '#15803d'))
PROGRESS_BANDS = ((0, 19, '严重不符合', '#dc2626'), (20, 39, '不符合', '#c2410c'),
                  (40, 59, '一般', '#a16207'), (60, 79, '符合', '#0f766e'),
                  (80, 100, '非常符合', '#15803d'))


def progress_band(value):
    """Numeric display tier only; does not override the teaching decision."""
    if value is None:
        return '#64748b', '暂无法评分'
    for lower, upper, label, color in PROGRESS_BANDS:
        if lower <= value <= upper:
            return color, label
    raise ValueError('分数必须在0—100之间。')


def score_band(value):
    if value is None:
        return '#64748b', '暂无法评分'
    for lower, upper, label, color in SCORE_BANDS:
        if lower <= value <= upper:
            return color, label
    raise ValueError('分数必须在0—100之间。')


def decision_style(score):
    """Use the stored decision, never infer passing from the final number alone."""
    label = score.get('等级')
    if label in ('可见项参考分', '无法评分', '待复核', '待检测'):
        return '#a16207', label
    for _, _, name, color in SCORE_BANDS:
        if label == name:
            return color, label
    return '#64748b', '历史评分'


def scale_position(value):
    """Linear display scale; each fifth represents 20 points, independent of gates."""
    return 50 if value is None else value


def validate_dimensions(dimensions):
    if not isinstance(dimensions, dict) or set(dimensions) != {name for name, _ in DIMENSIONS}:
        raise ValueError('六维评分必须包含完整的六个指定维度。')
    normalized = {}
    for name, maximum in DIMENSIONS:
        item = dimensions[name]
        if not isinstance(item, dict) or set(item) != {'分数', '理由'}:
            raise ValueError('每个维度必须包含分数和简短理由。')
        value, reason = item['分数'], item['理由']
        if value is not None and (type(value) is not int or not 0 <= value <= maximum):
            raise ValueError(f'{name}得分应为0—{maximum}的整数，无法判断时为null。')
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 24:
            raise ValueError('每项评分理由应为24字以内的短句。')
        normalized[name] = {'分数': value, '理由': reason.strip()}
    return normalized


def round_ratio(numerator, denominator):
    return (numerator * 2 + denominator) // (denominator * 2)


def critical_findings(dimensions, defects=(), phenomena=()):
    """Use reported visual evidence, never YOLO confidence, causes or advice.

    This is a conservative teaching rule, not confirmation by physical testing.
    A bare keyword, explicit negative or normal-texture comparison is insufficient.
    """
    reports = [*defects, *phenomena, *(item['理由'] for item in dimensions.values())]
    found = []
    names = r'(?:气孔|夹渣|裂纹|开裂|烧穿|咬边|焊瘤|未熔合|未焊透|弧坑)'
    negative_list = re.compile(r'(?:未见|未发现|未检出|没有|无|已排除)(?:明显|可见|明显的)?'
                               + names + r'(?:(?:[、及和与或\s]*)' + names + r')*')
    for name, word, evidence in (
        ('裂纹', r'裂纹|开裂|裂隙', r'纵向|横向|分叉|开口|裂隙|线状|贯穿|延伸|断续|中部|中心|两侧|焊趾'),
        ('烧穿', r'烧穿', r'贯穿孔|穿孔|孔洞|熔穿|穿透')):
        for report in reports:
            for clause in re.split(r'[，,。；;！!？?\n]|但是|但|然而', report):
                cleaned = negative_list.sub('', clause)
                if not re.search(word, cleaned):
                    continue
                if re.search(r'不是|并非|不属于|不能认定|不能判断|无法判断|无法确认|未能确认|不能排除|无法排除|未能排除|已排除|无.{0,5}依据|无.{0,5}证据', cleaned):
                    continue
                if re.search(r'(?:裂纹|开裂|烧穿)(?:不存在|不明显|不可见|未见)', cleaned):
                    continue
                if re.search(evidence, cleaned):
                    found.append({'类型': name, '依据': clause.strip(),
                                  '性质': '图像判断，非实测确认'})
                    break
            else:
                continue
            break
    return found


def evaluate_quality(dimensions, defects=(), phenomena=()):
    """Normalize without early rounding and apply minimum-axis teaching thresholds.

    Half-up rounding is used for the final integer (e.g. 94.5 -> 95).
    Only the six visible appearance axes determine this teaching assessment.
    """
    raw = validate_dimensions(dimensions)
    result = {}
    for name, maximum in DIMENSIONS:
        value = raw[name]['分数']
        result[name] = {'得分': value, '满分': maximum, '理由': raw[name]['理由'],
                        '分数': None if value is None else round_ratio(value * 100, maximum)}
    incomplete = [name for name, item in raw.items() if item['分数'] is None]
    visible = [(name, maximum) for name, maximum in DIMENSIONS if raw[name]['分数'] is not None]
    coverage = sum(maximum for _, maximum in visible)
    sufficient = len(visible) >= MIN_VISIBLE_DIMENSIONS and coverage >= MIN_VISIBLE_WEIGHT
    base = minimum = final = penalty = exact_base = combined = None
    if sufficient:
        exact_base = Fraction(sum(raw[name]['分数'] for name, _ in visible) * 100, coverage)
        minimum = min(Fraction(raw[name]['分数'] * 100, maximum) for name, maximum in visible)
        combined = (BASE_PERCENT * exact_base + MINIMUM_PERCENT * minimum) / 100
        final = round_ratio(combined.numerator, combined.denominator)
        # Round the displayed base only after computing the final from exact values.
        base = round_ratio(exact_base.numerator, exact_base.denominator)
        penalty = base - final
    numeric = score_band(final)[1]
    grade = numeric
    if final is not None and final >= PASS_SCORE:
        grade = ('非常符合' if final >= EXCELLENT_SCORE and minimum >= EXCELLENT_MINIMUM else
                 '符合' if minimum >= PASS_MINIMUM else '需改进')
    blockers = []
    if incomplete:
        grade = '可见项参考分' if sufficient else '无法评分'
        blockers.append(f'按{len(visible)}/6项可见项目评价，权重覆盖{coverage}%')
        blockers.append('未评分：' + '、'.join(incomplete))
    if final is not None and final < PASS_SCORE:
        blockers.append(f'最终分未达{PASS_SCORE}')
    if minimum is not None and minimum < PASS_MINIMUM:
        blockers.append(f'单项最低分未达{PASS_MINIMUM}')
    critical = critical_findings(raw, defects, phenomena)
    before_cap = final
    critical_penalty = 0 if final is not None else None
    if critical:
        if final is not None:
            final = min(final, CRITICAL_SCORE_CAP)
            critical_penalty = before_cap - final
        grade = '不符合'
        blockers.insert(0, '关键缺陷限分：' + '、'.join(item['类型'] for item in critical))
    numeric = score_band(final)[1]
    passed = grade in ('符合', '非常符合')
    goal = '已达到' if passed else grade if grade in ('无法评分', '可见项参考分') else '未达到'
    def exact(value):
        return None if value is None else {'numerator': value.numerator, 'denominator': value.denominator}
    calculation = {
        'version': 1, 'raw_total': sum(raw[name]['分数'] for name, _ in visible),
        'visible_weight': coverage, 'visible_count': len(visible), 'sufficient': sufficient,
        'base_exact': exact(exact_base), 'minimum_exact': exact(minimum),
        'combined_exact': exact(combined), 'base_percent': BASE_PERCENT, 'minimum_percent': MINIMUM_PERCENT,
        'rounding': 'half_up', 'before_cap': before_cap, 'final': final,
        'critical_cap': CRITICAL_SCORE_CAP if critical else None,
        'pass_score': PASS_SCORE, 'pass_minimum': PASS_MINIMUM,
        'excellent_score': EXCELLENT_SCORE, 'excellent_minimum': EXCELLENT_MINIMUM,
        'minimum_visible_count': MIN_VISIBLE_DIMENSIONS, 'minimum_visible_weight': MIN_VISIBLE_WEIGHT,
        'axes': [{'name': name, 'raw': raw[name]['分数'], 'maximum': maximum,
                  'normalized_exact': exact(None if raw[name]['分数'] is None else Fraction(raw[name]['分数'] * 100, maximum))}
                 for name, maximum in DIMENSIONS],
    }
    return result, {'分数': final, '基础分': base, '短板惩罚': penalty,
                    '限分前得分': before_cap, '关键缺陷扣分': critical_penalty,
                    '关键缺陷': critical, '分数上限': CRITICAL_SCORE_CAP if critical else None,
                    '最低项分': None if minimum is None else round(float(minimum), 2),
                    '最终分': final, '数值等级': numeric, '等级': grade,
                    '是否达到教学目标': goal, '达标': passed,
                    '判定依据': blockers or ['最终分和单项最低分达到外观教学门槛'],
                    '未评分维度': incomplete, '可评维度数': len(visible), '可评权重': coverage,
                    '评价范围': '可见项目外观参考' if incomplete else '六维外观教学评价',
                    '评分类型': ('可见项参考分' if sufficient else '无法评分') if incomplete else '短板约束综合分',
                    '评分版本': RUBRIC_VERSION, '计算明细': calculation}


def evaluate_dimensions(dimensions):
    result, score = evaluate_quality(dimensions)
    return result, score['分数'], score['评分类型']


def weighted_score(dimensions):
    return evaluate_dimensions(dimensions)[1]
