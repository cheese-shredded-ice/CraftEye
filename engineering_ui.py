"""Project-specific engineering evidence with explicit dependency provenance."""
import hashlib
import json
from html import escape
from pathlib import Path
import streamlit as st
from analysis_audit import table
from scoring import BASE_PERCENT, MINIMUM_PERCENT, CRITICAL_SCORE_CAP, PASS_SCORE, PASS_MINIMUM


ROOT = Path(__file__).resolve().parent
IMPLEMENTATIONS = {
    '重点区域选取': 'focus_regions.py', '统一评分与教学门槛': 'scoring.py',
    '教学任务约束': 'prompts/welding_v4.md', '请求与结构校验': 'ai_analysis.py',
    '运算过程留痕': 'analysis_audit.py', '记录持久化': 'recognition_history.py',
    '真实成长轨迹': 'growth_chart.py', '本地推理适配': 'onnx_backend.py',
}


def evidence_payload(root=ROOT):
    def read(name):
        path = root / name
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
    return {'product':'CraftEye', 'scope':'项目定制开发与公开模型依赖的可核验清单',
            'implementation':[{'module':title,'file':file,'sha256':hashlib.sha256((root/file).read_bytes()).hexdigest() if (root/file).exists() else None} for title,file in IMPLEMENTATIONS.items()],
            'detector_source':read('models/source.json'),
            'verification_snapshot':read('assets/engineering/verification.json'),
            'onnx_parity_snapshot':read('assets/engineering/model-parity.json'),
            'evidence_sources':read('assets/engineering/sources.json')}


def engineering_html(data):
    source = data.get('detector_source') or {}
    verification = data.get('verification_snapshot') or {}
    parity = data.get('onnx_parity_snapshot') or {}
    metrics = verification.get('test_metrics', {})
    body = '<section class="engineering-report"><p class="engineering-lead">面向中职焊接实训的可追溯评价工作流</p>'
    body += '<div class="architecture-flow">' + ''.join(f'<div><b>{i:02d}</b><strong>{title}</strong><span>{detail}</span></div>' for i,(title,detail) in enumerate([
        ('本地定位','YOLO 检测与原图留存'), ('区域证据','60%门槛 · 无标注裁图'), ('视觉描述','目标约束 · 六维结构输出'),
        ('规则计算','短板约束 · 缺陷限分'), ('教学闭环','建议 · 留档 · 成长对比')],1)) + '</div>'
    body += '<h3>项目定制的核心实现</h3>'
    body += table(['模块','设计逻辑','可核验代码'],[
        ['区域证据选择','缺陷优先；保留框内小缺陷；扩边裁图；检测置信度只用于定位。','focus_regions.py'],
        ['六维短板约束',f'{BASE_PERCENT}%基础分 + {MINIMUM_PERCENT}%最低项；精确分数计算与输出取整。','scoring.py'],
        ['质量门槛与教学目标',f'符合需最终分≥{PASS_SCORE}且各项≥{PASS_MINIMUM}；图像关键缺陷触发最高{CRITICAL_SCORE_CAP}分。','scoring.py'],
        ['教学语境与输出校验','面向中职学生；优先检查中部及两侧线状开裂；区分鱼鳞纹；限定六维与简短建议。','prompts/welding_v4.md / ai_analysis.py'],
        ['过程留痕与版本追溯','原图、检测图、裁图指纹、计算快照、评分规则随记录保存。','analysis_audit.py / recognition_history.py'],
        ['本地化交付','Windows CPU 推理、ONNX 适配、摄像头截取、单屏响应式布局。','onnx_backend.py / camera_ui.py / workspace.css'],
    ])
    body += '<details class="audit-step"><summary><b>验证与训练来源</b><small>展开查看原始记录与指标范围</small></summary><div class="audit-step-body">'
    if metrics:
        body += table(['历史测试快照','记录值'],[
            ['独立测试集规模',f'{metrics.get("test_images", "—")} 张'],
            ['Precision',f'{metrics["precision"]:.4f}'],['Recall',f'{metrics["recall"]:.4f}'],
            ['mAP@50',f'{metrics["mAP50"]:.4f}'],['mAP@50:95',f'{metrics["mAP50_95"]:.4f}'],
        ])
        body += '<p>以上是项目留存的检测模型测试快照，针对公开数据的三类目标检测，不是九类缺陷识别准确率，也不是教学评分准确率。</p>'
    else:
        body += '<p>当前目录未提供检测验证快照。</p>'
    if parity:
        body += f'<p>ONNX 转换一致性：{parity["images"]}张图片、{parity["threshold_checks"]}组阈值检查、{parity["matched_detections"]}个匹配框；数量和类别{"一致" if parity["all_detection_counts_and_classes_match"] else "存在差异"}。最大框坐标差 {parity["max_box_difference_pixels"]:.6f} 像素。</p>'
    body += f'<p>检测权重来源：{escape(source.get("repo","未提供"))}；版本：<code>{escape(source.get("revision","未提供"))}</code>。</p>'
    if source.get('trained_locally') is False:
        body += '<p><b>训练记录：当前使用作者公开训练的权重，未在本项目重新训练。</b>作者记录100轮训练；项目已完成本地适配、复测和场景化评价开发。当前证据不支持“自主训练基础模型”的表述。</p>'
    else:
        body += '<p>自主训练需要数据版本、训练配置、日志、权重及独立验证报告共同佐证；当前面板仅展示已提供的材料。</p>'
    body += '<p>视觉语义分析使用配置的通义千问服务；系统自行实现任务约束、数据流、规则计算、记录管理与展示。模型不决定权重、总分或达标门槛。</p></div></details>'
    body += '<details class="audit-step"><summary><b>代码与证据指纹</b><small>对应当前运行目录，可下载核验</small></summary><div class="audit-step-body">'
    body += table(['模块','代码文件','SHA-256'],[[x['module'],x['file'],x['sha256'] or '文件缺失'] for x in data['implementation']])
    body += '<p>指纹用于锁定展示版本，不单独证明作者身份或模型精度。源代码、Git记录和可复现测试共同构成开发证据。</p></div></details></section>'
    return body


@st.dialog('技术与验证', width='large')
def engineering_dialog():
    data = evidence_payload()
    st.download_button('下载技术证据清单',json.dumps(data,ensure_ascii=False,indent=2),'CraftEye-technical-evidence.json','application/json',on_click='ignore')
    st.html(engineering_html(data))


def render_engineering_entry():
    if st.button('技术与验证', key='engineering_entry',use_container_width=True):
        engineering_dialog()
