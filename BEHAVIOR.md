# 实训行为观察模块

网页进入 **实训行为**。本模块用本地模型检测可观察的训练行为，不输出心理专注度、情绪、能力推断或自动成绩。焊缝质量评分保持原有逻辑。

## 功能

- 示例视频、上传视频和浏览器摄像头三种输入；上传最长 10 分钟。
- 统计单人在工位区域内/外的时间。工位在“观察设置”中调整，预览青色框即区域；按人体框中心判断，不等同于是否正在施焊。
- 肩、髋关键点组成的二维躯干倾角。默认超过 45°、连续 2 秒形成事件，参数可调。这不是医学或工效学评分。
- 面罩、手套、围裙、鞋类四态观察：检出装备、异常线索、证据不一致、未观察到。直接检出“未佩戴”等类别才生成异常线索；没有检测框不代表未佩戴。
- 手机与可见手腕邻近的持续事件，不推断使用目的。手机规则经过测试，但测试视频没有带标注的手机使用正例，不能给出检测准确率。
- 事件起止时间、持续时长、视频定位回放、标注视频和 JSON 报告下载。摄像头结束后冻结结果、保存报告，重新开始时重新计时。
- 统计使用视频/采集时间，不用推理耗时充当行为时长。断流、多人与位置突变打断事件连续性。

## 开源来源

1. [Ultralytics YOLO11](https://github.com/ultralytics/ultralytics)：`yolo11n-pose.pt` 用于人体关键点，`yolo11n.pt` 用于手机目标。AGPL-3.0。
2. [Ergonomie 4.0](https://github.com/ayoub-elkhader/ergonomie-4.0-ppe-detection)：采用作者已训练的焊接 PPE YOLOv8s 权重 `weights/best.pt`，本地名为 `models/behavior/welding-ppe.pt`。参考其装备类别与证据规则，重新实现适配本项目的时序统计和界面。AGPL-3.0。

权重来源、校验值、许可证和 NOTICE 保存在 `models/behavior/`。上游 README、ppe.py、posture.py、settings.py 已下载到 `outputs/behavior-upstream/` 供查阅，没有执行其安装脚本或替换现有 Python 环境。

本机模型已下载好。其他源码环境可执行：

```powershell
& .\.venv\Scripts\python.exe scripts\setup_behavior.py --videos
```

下载使用 `assets/behavior/resources.json` 中的地址与 SHA-256 校验；内容改变时不会静默覆盖。运行本模块无需云端密钥和联网。

## 网上下载的测试视频

素材在 `outputs/behavior-samples/`，不提交视频到 Git，不自动放入发布包。

| 文件 | 来源与使用范围 | 测试用途 |
|---|---|---|
| workshop-demo.mp4，10.37秒 | [上游演示](https://github.com/ayoub-elkhader/ergonomie-4.0-ppe-detection/blob/main/videos/demo_atelier.mp4)；上游未记录出镜授权，仅本地测试 | 实际为拍摄屏幕中的实训画面，是模型烟雾测试，不能代表独立现场验证 |
| mig-welding.webm，37秒 | [Chris MacDonald / Wikimedia Commons](https://commons.wikimedia.org/wiki/File:MIG_welding.webm)，CC BY 3.0 | 仅焊点可见的低光负例，验证未知状态 |
| college-welding.mp4，120.25秒 | [EC3 Welding Pathway 2026 / Internet Archive](https://archive.org/details/hcectvky-EC3_Welding_Pathway_2026)；无明确再分发许可，仅本地测试 | 独立学校视频，包含施焊、访谈、特写、转场、片头，测试泛化 |

## 实际验证

2026-11-12，本机 CPU，三个模型均真实推理：

- 上游演示：单人可观察约 9.03 秒，面罩检出约 8.37 秒，手套约 3.67 秒，围裙约 4 秒。
- 低光视频：37 秒全部无法观察，没有生成离岗或装备违规事件，也没有填造评分。
- 独立学校视频：完整处理 120.25 秒；单人可观察约 50.05 秒，约 70.20 秒无法判断；面罩与手套均有检出，但装备覆盖率明显低于上游演示。
- 三模型平均每个采样帧约 0.13–0.16 秒（无其他重负载时）。视频约每秒采样 3 帧，摄像头取最新帧，避免排队延迟。
- 78 项单元/媒体测试通过，其中新增 13 项，覆盖证据冲突、遮挡、多人与跳变、持续阈值、时间戳、无效视频、取消和视频编码。
- 浏览器验证视频上传、下载、回放稳定性、事件定位，以及下载视频驱动的模拟摄像头开始/停止/重新开始。不是物理摄像头实拍验证。
- 1280×720、1366×768、1920×1080 单屏布局通过；内容较多时面板内部滚动。
- 原有焊缝图片分析、摄像头截取自动分析、报告与记录的浏览器回归通过。云端响应经过模拟，没有消耗真实 API 配额。

```powershell
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv\Scripts\python.exe scripts\verify_behavior_models.py
# 浏览器测试需要普通 app.py 服务运行在8516端口
& .\.venv\Scripts\python.exe -m streamlit run app.py --server.port=8516
& .\.venv\Scripts\python.exe scripts\test_behavior_browser.py
```

验证结果、截图在 `outputs/behavior-check/`。新分析保存到 `outputs/behavior/<运行ID>/`：视频包含 `report.json`、逐帧统计 `samples.json`、`annotated.mp4`；摄像头当前保存报告和会话内冻结画面，不保存原始连续录像。

## 限制

使用固定机位、单工位、单个学生，尽量覆盖头部、肩髋、双手和工位。这不是多人身份跟踪系统，出现多人或目标丢失时不判断是谁离岗。片头、剪辑、镜头移动也不能作为真实离岗依据。

PPE 模型来自小规模单车间数据；独立视频中有漏检和误检，包括把抬起的面罩仍检为面罩。“检出装备”不等于正确佩戴或安全达标，未观察到鞋类不能默认合格。阈值是教学观察设置，不是工业安全认证标准。

这次更新的是源码工程，之前的 v3.0 ZIP 保持原样。后续如需把行为模型放入精简包，需要同步适配其推理运行环境。
