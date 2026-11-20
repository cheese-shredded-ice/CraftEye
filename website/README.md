# 网页运行代码

`website/` 是 CraftEye 网页的唯一运行代码目录。根目录的 `app.py` 只是兼容启动入口，启动器和 Streamlit 仍然可以直接运行它。

## 目录分工

- `app.py`：页面入口，组合图片识别、摄像头、识别记录和数据浏览。
- `inference.py`、`onnx_backend.py`：本地 YOLO / ONNX 检测与检测框绘制。
- `ai_analysis.py`、`ai_ui.py`、`prompts/`：综合视觉分析请求、结构校验和教学提示词。
- `scoring.py`、`teaching_report_ui.py`、`score_ui.py`：六维评分、雷达图和评分展示。
- `camera.py`、`camera_ui.py`：摄像头帧处理、手动/自动识别。
- `recognition_history.py`、`history_ui.py`：识别记录、原图、检测图和成长曲线。
- `workspace_ui.py`、`workspace.css`、`dashboard_visuals.py`：页面布局、样式和视觉素材加载。

模型、数据集、图片素材和本地记录仍放在项目根目录的 `models/`、`dataset/`、`assets/`、`outputs/`，这样资源路径和便携版打包都保持稳定。
