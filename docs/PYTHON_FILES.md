# Python 文件说明

当前仓库只保留当前网页、模型推理、评分记录和开发验证需要的 Python 文件。停用的“实训行为”模块及其专用测试已移除。

## 网页运行核心

| 文件 | 作用 |
| --- | --- |
| `app.py` | Streamlit 网页入口，组合四个页面标签 |
| `common.py` | 模型、数据集和类别路径配置 |
| `workspace_ui.py` | 页眉、工作台布局和通用检测摘要 |
| `workspace.css` | 单屏网页样式 |
| `dashboard_visuals.py` | 页面图标和视觉素材 |

## 检测与摄像头

| 文件 | 作用 |
| --- | --- |
| `inference.py` | 图片推理、检测框绘制和标签解析 |
| `onnx_backend.py` | 精简版 ONNX Runtime CPU 推理后端 |
| `camera.py` | 摄像头帧处理器 |
| `camera_ui.py` | 摄像头手动/自动识别页面 |
| `focus_regions.py` | 筛选置信度高于 60% 的重点区域 |
| `defect_references.py` | 缺陷参考图片匹配 |

## 综合分析、评分与记录

| 文件 | 作用 |
| --- | --- |
| `ai_analysis.py` | 调用综合分析接口并校验结构化结果 |
| `ai_ui.py` | 综合分析状态、报告和建议界面 |
| `advice.py` | 教学场景的现场现象选项 |
| `scoring.py` | 六维评分、短板约束和等级判断 |
| `score_ui.py` | 综合分仪表和分档进度条 |
| `teaching_report_ui.py` | 六维雷达图和维度理由 |
| `analysis_audit.py` | 分析过程和评分快照 |
| `recognition_history.py` | SQLite 记录、原图和检测图保存 |
| `history_ui.py` | 识别记录、详情、删除、导出和成长曲线页面 |
| `demo_history.py` | 首次启动时写入同一数据库的 60 条训练成长记录 |
| `growth_chart.py` | 训练趋势计算和图表数据 |
| `image_library_ui.py` | 示例图片和历史原图选择 |
| `engineering_ui.py` | 设置中的技术与验证信息 |

## 命令行和打包工具

这些文件不在网页启动时导入，按需要运行：

- `predict.py`：命令行单张图片检测。
- `scripts/download_dataset.py`、`scripts/download_model.py`：下载并校验数据和模型。
- `scripts/export_portable_model.py`、`scripts/verify_onnx_parity.py`：导出和比对 ONNX 模型。
- `scripts/build_portable.py`、`scripts/preset_portable_key.py`、`scripts/verify_portable_archive.py`：构建、预设和验证 Windows 便携版。
- `scripts/verify_install.py`：检查本地安装、数据集和模型。
- `scripts/ai_test_app.py`：测试用的本地分析服务。

## 浏览器回归测试

`scripts/test_*.py` 是按功能拆分的 Playwright 测试；`tests/test_*.py` 是单元测试。它们不属于网页运行依赖，但用于修改后验证功能。

## Windows 启动

`packaging/windows/launcher.py` 是便携版后台启动器。网页开发时直接运行 Streamlit，发布包通过 `启动网页.cmd` 调用它。
