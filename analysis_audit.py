"""Auditable inputs and executable rules, never invented model reasoning."""
import base64
import hashlib
import io
import json
from html import escape
from PIL import Image
from scoring import DIMENSIONS, RUBRIC_VERSION, evaluate_quality
from focus_regions import focus_regions, MAX_FOCUS_CROPS


def build_audit(report, payload, original_size, rows):
    images = []
    for item in payload['messages'][0]['content']:
        if item['type'] == 'image_url':
            data = base64.b64decode(item['image_url']['url'].split(',', 1)[1])
            with Image.open(io.BytesIO(data)) as image:
                images.append({'size': list(image.size), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    raw = {name: {'分数': report['dimensions'][name]['得分'], '理由': report['dimensions'][name]['理由']} for name, _ in DIMENSIONS}
    axes, recalculated = evaluate_quality(raw, report['sections']['缺陷类型'], report['sections']['图中现象'])
    checks = [
        {'name': '六维字段与分值范围', 'passed': True, 'detail': '已通过结构与分值范围校验；不可见项保留空值。'},
        {'name': '统一评分函数复算', 'passed': all(report['score'].get(k) == v for k, v in recalculated.items()) and axes == report['dimensions'],
         'detail': '用同一评分函数复算标准化、短板惩罚、限分及教学判定。'},
        {'name': '图像数量与裁图配置',
         'passed': (len(images) == 2 + len(report['focus_regions'])
                    and report['focus_regions'] == focus_regions(rows, original_size)[:MAX_FOCUS_CROPS]),
         'detail': '核对原图、检测概览与裁图数量，并按检测数据复算裁图配置；实际提交图像另存指纹。'},
    ]
    return {'version': 1, 'original_size': list(original_size), 'detections': rows,
            'images': images, 'request_sha256': hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'checks': checks, 'rubric_version': RUBRIC_VERSION,
            'scope': '校验数据结构与计算一致性，不代表视觉判断已被实测证实。'}


def number(value):
    if isinstance(value, dict) and 'numerator' in value:
        value = value['numerator'] / value['denominator']
    return '—' if value is None else f'{value:.2f}'.rstrip('0').rstrip('.')


def table(headers, rows):
    return '<div class="audit-table-wrap"><table><thead><tr>' + ''.join(f'<th>{escape(str(x))}</th>' for x in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{escape(str(x))}</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def image_url(image):
    resized = image.convert('RGB').copy()
    resized.thumbnail((360, 200))
    output = io.BytesIO()
    resized.save(output, 'JPEG', quality=80)
    return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')


def audit_html(report, original=None, inputs=None):
    audit = report.get('audit') or {}
    calc = report.get('score', {}).get('计算明细') or {}
    inputs = inputs or {}
    score = report['score']
    checked = bool(audit.get('checks')) and all(x['passed'] for x in audit['checks'])
    status = ('计算校验通过' if checked else '计算校验发现差异' if audit.get('checks')
              else '历史记录 · 部分依据未留存')
    parts = [f'<details class="analysis-audit"><summary><span>运算与分析过程</span><small>{status}</small></summary><div class="audit-body">']
    def step(title, subtitle, body):
        return f'<details class="audit-step"><summary><b>{title}</b><small>{escape(subtitle)}</small></summary><div class="audit-step-body">{body}</div></details>'
    size = audit.get('original_size', inputs.get('original_size', []))
    detections = audit.get('detections', inputs.get('detections', []))
    regions = report.get('focus_regions', [])
    selected = {x['detection_index'] for x in regions}
    body = f'<p>训练目标：{escape(report.get("learning_goal", "未留存"))}</p><p>原图尺寸：{escape(" × ".join(map(str, size))) or "未留存"}；检测框 {len(detections)} 个；重点裁图 {len(regions)} 张。</p>'
    if 'manual_observations' in inputs:
        body += '<p>人工选择的现场现象：' + escape('；'.join(inputs['manual_observations']) or '未填写') + '。</p>'
    if 'process_context' in inputs:
        body += '<p>补充工艺信息：' + escape(inputs['process_context'] or '未填写') + '。</p>'
    body += '<p>原图与检测概览共同输入；置信度 &gt;60% 的有效框按缺陷优先、置信度排序，去重后最多取8处。裁图向四周扩展12%（至少8像素），保留周边纹理。</p>'
    if original is not None:
        figures = f'<figure><img alt="运算输入原图" src="{image_url(original)}"><figcaption>原始输入</figcaption></figure>'
        for i, region in enumerate(regions):
            figures += f'<figure><img alt="重点裁图{i+1}" src="{image_url(original.crop(tuple(region["crop_box"])))}"><figcaption>重点{i+1} · 框#{region["detection_index"]+1}</figcaption></figure>'
        body += '<div class="audit-images">' + figures + '</div>'
    rows = []
    for i, row in enumerate(detections):
        confidence = row.get('置信度')
        rows.append([i+1, row.get('类别', '—'), '—' if confidence is None else f'{confidence:.1%}',
                     ', '.join(str(row.get(k, '—')) for k in ['左','上','右','下']), '重点裁图' if i in selected else '仅保留检测记录'])
    body += table(['框号', '检测类别', '置信度', '坐标 L,T,R,B', '处理'], rows) if rows else '<p>无可用检测框记录；不据此推断焊缝无缺陷。</p>'
    body += '<p class="audit-note">置信度仅用于定位和裁图，不是焊接质量分，也不直接作为扣分依据。</p>'
    if audit.get('images'):
        body += table(['送入视觉模型的图像', '实际尺寸', '内容指纹 SHA-256'], [[('原图','检测概览')[i] if i<2 else f'重点裁图{i-1}', ' × '.join(map(str, x['size'])), x['sha256']] for i,x in enumerate(audit['images'])])
    parts.append(step('01 原始数据输入', f'{len(detections)}个检测框 · {len(regions)}张重点裁图', body))
    body = '<p>视觉模型输出六项原始分与图像依据；权重、总分和教学门槛由本地规则计算。</p>'
    if calc:
        body += table(['维度','原始分 / 满分','标准化计算','标准化分'], [[x['name'],f'{number(x["raw"])}/{x["maximum"]}',f'{number(x["raw"])} ÷ {x["maximum"]} × 100' if x['raw'] is not None else '不可见，保留空值', number(x['normalized_exact'])] for x in calc['axes']])
        if calc['sufficient']:
            body += f'<div class="audit-formula">A = {calc["raw_total"]} ÷ {calc["visible_weight"]} × 100 = {number(calc["base_exact"])}<br>M = 最低标准化分 = {number(calc["minimum_exact"])}<br>S₀ = 四舍五入（{calc["base_percent"]}% × A + {calc["minimum_percent"]}% × M）= {number(calc["before_cap"])}</div>'
        else:
            body += f'<p>仅有{calc["visible_count"]}项可评、覆盖{calc["visible_weight"]}%权重，不满足至少{calc["minimum_visible_count"]}项且覆盖{calc["minimum_visible_weight"]}%的要求，不计算总分。</p>'
        if not calc['sufficient']:
            body += '<p>基础分、最低项和最终分均未计算；不可见项不按零分处理。</p>'
        elif calc['critical_cap'] is not None:
            body += f'<p>关键缺陷限分：S = min（S₀, {calc["critical_cap"]}）= {number(calc["final"])}。</p>'
        else:
            body += f'<p>未触发关键缺陷限分，S = S₀ = {number(calc["final"])}。</p>'
        body += f'<p>展示基础分 {number(score.get("基础分"))} − 短板惩罚 {number(score.get("短板惩罚"))} − 关键缺陷扣分 {number(score.get("关键缺陷扣分"))} = 最终分 {number(score.get("分数"))}。</p><p class="audit-note">内部使用精确分数运算，仅在输出时四舍五入；此处小数为显示值。雷达图保留各项真实得分。</p>'
    else:
        body += '<p>旧记录未保存逐步运算快照，保留当时分数，不用当前规则重算旧分数。</p>'
    parts.append(step('02 分步运算逻辑', f'基础分 {number(score.get("基础分"))} → 最终分 {number(score.get("分数"))}', body))
    body = ''.join(f'<p class="audit-check">{"✓" if x["passed"] else "!"} {escape(x["name"])}：{escape(x["detail"])}</p>' for x in audit.get('checks', [])) or '<p>旧记录未保存校验快照。</p>'
    body += '<p class="audit-note">校验通过只表示数据格式与计算一致，视觉识别仍可能有误差。</p>'
    body += table(['教学判定依据', '保存值'], [[k, number(score.get(k)) if isinstance(score.get(k), (int,float)) else '；'.join(score.get(k, [])) if isinstance(score.get(k),list) else score.get(k,'未留存')] for k in ['可评维度数','可评权重','最低项分','等级','是否达到教学目标','判定依据']])
    for finding in score.get('关键缺陷', []):
        body += f'<p>限分依据 · {escape(finding["类型"])}：{escape(finding["依据"])}（{escape(finding["性质"])}）</p>'
    if calc:
        body += f'<p>完整六项符合：最终分≥{calc["pass_score"]}且每项≥{calc["pass_minimum"]}；非常符合：最终分≥{calc["excellent_score"]}且每项≥{calc["excellent_minimum"]}；关键缺陷规则优先。</p>'
    parts.append(step('03 中间结果校验', status, body))
    body = '<p>以下对比使用标准化分（0—100），与雷达图同源；短板惩罚不会改写单项评分。</p>'
    dimensions = report.get('dimensions', {})
    threshold = calc.get('pass_minimum')
    body += table(['维度','权重','标准化分','与单项目标差值','图像评价依据'], [[name,f'{weight}%',number(dimensions.get(name,{}).get('分数')), '—' if threshold is None or dimensions.get(name,{}).get('分数') is None else f'{dimensions[name]["分数"]-threshold:+d}', dimensions.get(name,{}).get('理由','未留存')] for name,weight in DIMENSIONS])
    body += f'<p>视觉分析服务：{escape(report.get("provider","未留存"))} / {escape(report.get("model","未留存"))}；本地评分版本：{escape(report.get("rubric_version","未留存"))}。</p>'
    parts.append(step('04 多维度对比分析', '六维真实得分 × 教学目标', body))
    parts.append('</div></details>')
    return ''.join(parts)
