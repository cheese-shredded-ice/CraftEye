"""Local teaching examples cropped from the reference sheet supplied by the user."""
from pathlib import Path
import re

from .common import ROOT

REFERENCE_DIR = ROOT / 'assets' / 'defect-references'
REFERENCES = {
    '气孔': ('porosity.jpg', '看表面：有圆形或不规则的小孔。'),
    '夹渣': ('slag.jpg', '看断面：金属内部夹有非金属残留。此示例是断面图。'),
    '裂纹': ('crack.jpg', '看裂口：细长的开裂，与普通划痕区分。'),
    '未焊透': ('incomplete-penetration.jpg', '看根部：接头底部没有完全焊透。此示例是断面图。'),
    '未熔合': ('lack-of-fusion.jpg', '看结合处：两侧金属没有充分熔合。此示例是断面图。'),
    '咬边': ('undercut.jpg', '看焊缝边缘：母材出现凹槽。'),
    '焊瘤': ('overlap.jpg', '看焊缝边缘：多余金属堆搭在母材上。'),
    '烧穿': ('burn-through.jpg', '看孔洞：焊接处出现贯穿孔。'),
    '弧坑': ('crater.jpg', '看收弧位置：末端留下凹坑。'),
}


def matched_references(classifications):
    """Match the declared type only, never incidental or negated words in evidence."""
    matches = []
    for item in classifications:
        match = re.match(r'^(?:疑似\s*)?([^：:]+)\s*[：:]', item.strip())
        if match:
            name = match.group(1).strip()
            if name in REFERENCES and name not in matches:
                matches.append(name)
    return matches
