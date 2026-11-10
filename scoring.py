"""Unified six-axis appearance teaching score with a weakest-axis penalty."""
from fractions import Fraction
DIMENSIONS = (
    ('成形质量', 20),
    ('焊道连续性', 20),
    ('焊趾过渡', 15),
    ('表面质量', 20),
    ('焊道走向稳定性', 15),
    ('焊后清洁度', 10),
)
RUBRIC_VERSION = 'welding-v7-appearance-direct-v1'
BASE_PERCENT = 80
MINIMUM_PERCENT = 20
PASS_SCORE, PASS_MINIMUM = 85, 70
EXCELLENT_SCORE, EXCELLENT_MINIMUM = 93, 85
SCORE_FORMULA = f'最终分 = {BASE_PERCENT}%基础分 + {MINIMUM_PERCENT}%最低项'
SCORE_BANDS = ((0, 59, '严重不符合', '#dc2626'), (60, 74, '不符合', '#c2410c'),
               (75, PASS_SCORE - 1, '需改进', '#a16207'), (PASS_SCORE, EXCELLENT_SCORE - 1, '符合', '#0f766e'),
               (EXCELLENT_SCORE, 100, '非常符合', '#15803d'))


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
    if label in ('无法评分', '待复核', '待检测'):
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


def evaluate_quality(dimensions):
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
    base = minimum = final = penalty = None
    if not incomplete:
        base = sum(item['分数'] for item in raw.values())
        minimum = min(Fraction(raw[name]['分数'] * 100, maximum) for name, maximum in DIMENSIONS)
        combined = (BASE_PERCENT * base + MINIMUM_PERCENT * minimum) / 100
        final = round_ratio(combined.numerator, combined.denominator)
        penalty = base - final
    numeric = score_band(final)[1]
    grade = numeric
    if final is not None and final >= PASS_SCORE:
        grade = ('非常符合' if final >= EXCELLENT_SCORE and minimum >= EXCELLENT_MINIMUM else
                 '符合' if minimum >= PASS_MINIMUM else '需改进')
    blockers = []
    if incomplete:
        grade = '无法评分'
        blockers.append('图片依据不足：' + '、'.join(incomplete))
    if final is not None and final < PASS_SCORE:
        blockers.append(f'最终分未达{PASS_SCORE}')
    if minimum is not None and minimum < PASS_MINIMUM:
        blockers.append(f'单项最低分未达{PASS_MINIMUM}')
    passed = grade in ('符合', '非常符合')
    goal = '已达到' if passed else grade if grade == '无法评分' else '未达到'
    return result, {'分数': final, '基础分': base, '短板惩罚': penalty,
                    '最低项分': None if minimum is None else round(float(minimum), 2),
                    '最终分': final, '数值等级': numeric, '等级': grade,
                    '是否达到教学目标': goal, '达标': passed,
                    '判定依据': blockers or ['最终分和单项最低分达到外观教学门槛'],
                    '未评分维度': incomplete, '评价范围': '六维外观教学评价', '评分类型': '短板约束综合分' if final is not None else '无法评分',
                    '评分版本': RUBRIC_VERSION}


def evaluate_dimensions(dimensions):
    result, score = evaluate_quality(dimensions)
    return result, score['分数'], score['评分类型']


def weighted_score(dimensions):
    return evaluate_dimensions(dimensions)[1]
