# 系统功能检查（2026-11-20）

检查当前开发目录中的启用功能：图片识别、摄像头、综合分析、评分、记录与成长曲线、图片库、数据标注浏览、设置、下载和启动脚本。未重新打包，也未提交 Git。实训行为入口按现有设置保持关闭。

## 本轮修复

- **分析任务卡住**：清空图片后仍会回收已完成的后台任务，不再占用后续分析入口。
- **错误状态布局缺失**：未配置密钥、接口报错、输入变化时保留同一套零分仪表、状态条和视图按钮；错误可重试。
- **摄像头暂停占位和重复按钮**：冻结画面与状态控件使用固定容器；暂停时同时隐藏实时流及其布局包装层。识别方式、现场现象改为单独一行。重新拍摄使用一次性启动指令。
- **历史删除刷新异常**：删除回调只保存通知，正常渲染时再显示，避免 fragment 回调改写页面顶部。
- **完整报告漏分析内容**：图片和摄像头报告包含匹配当前输入的六维评分、最终分、教学建议及运算留痕；切换图片、现场现象或模型后不导出旧分析。尚未完成分析时仍可导出本地检测结果。
- **损坏输入**：无效上传不再允许点击识别；数据集图片或标注损坏时局部提示，不拖垮其他标签页。
- **接口边界**：明确按 UTF-8 读取中文流式响应，限制完整响应大小；截断、网络中断和非法接口地址给出可读错误并释放连接。
- **启动恢复**：允许 PT/ONNX 权重；损坏或丢失进程记录时检查端口进程并复用同一应用，避免重复启动；停止脚本核对具体应用和端口。

记录删除后的连续展示序号、单库内置记录、默认手动拍摄和现有评分规则保留。数据库主键不会因显示编号变化而修改。

## 验证结果

| 范围 | 实际验证 | 证据 |
| --- | --- | --- |
| 单元回归 | 112 项通过；含评分、裂纹限分、缺项、并发保存、删除回滚、流式边界和原图保存 | outputs/system-check/unit-tests.log |
| 本地模型与数据库文件 | 校验 4062 个源文件、2028 张图片及标注、模型 SHA；真实 CPU 推理成功 | outputs/system-check/installation.json |
| 综合分析界面 | 无密钥、401 重试、分析时清空图片再识别、配置变化、导出和技术证据弹窗 | outputs/system-check/system-regression.json |
| 图片操作 | 原图/检测图切换、人工现场现象选择、PNG 和检测 JSON 下载、完整报告下载 | outputs/system-check/image-controls.json |
| 评分与响应式 | 关键裂纹限制为最高 59 分；缺项显示可见项参考；五种视口切换雷达与建议 | outputs/system-check/feedback-*.png |
| 真实云端接口 | 使用本机预设密钥实际调用一次 qwen3-vl-plus；六个维度依次收到，报告校验通过；未写入历史 | outputs/system-check/live-analysis.json |
| 摄像头 | 假摄像头输入真实 YOLO 推理；默认手动，超过 10 帧不会自动拍摄；连续重新拍摄、关闭所有媒体轨道、切换自动模式、阈值更新、导出 | outputs/camera-check/verification.json |
| 摄像头布局 | 冻结画面在 800×450、1024×600、1280×720、1366×768、1920×1080、805×1365 检查按钮边界 | scripts/test_camera_browser.py |
| 记录 | 六种视口对齐、历史详情 ZIP、原图像素、旧记录、翻页删除、刷新、批量删除关联清理 | outputs/history-detail-check/verification.json |
| 删除后样式 | 连续删除三条并等待刷新，样式与图片清理保持正常 | scripts/test_history_style_browser.py |
| 图片库 | 20 张缩略图滚轮浏览、原图历史、上传/图库切换和检测，三种视口 | scripts/test_image_library_browser.py |
| 启停 | 独立端口实际启动、重复启动复用、坏 PID 恢复、关闭并确认释放端口 | outputs/system-check/launcher.txt |
| 运行网站 | 8501 页面和四个标签页只读检查，无页面异常，当前摄像头模块已加载 | outputs/system-check/production-smoke.json |

浏览器自动化使用 8514/8517 测试服务及 outputs/ai-check/history-test.sqlite3，删除测试不操作用户记录。真实接口的密钥不写入报告。原有历史验证快照保留，新安装检查另存 outputs/system-check/installation.json。

摄像头自动化验证的是浏览器、WebRTC 与推理链路，不替代具体手机、DroidCam 驱动或物理摄像头的兼容性验证。一次真实接口成功也不代表所有焊接图片的判别精度；此次没有修改模型权重或重新训练。

## 复现

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/verify_install.py --output outputs/system-check/installation.json

# 单独终端启动测试网站，以下浏览器脚本按顺序执行（共用测试库）
.\.venv\Scripts\python.exe -m streamlit run scripts/ai_test_app.py --server.port=8514 --server.address=127.0.0.1 --server.headless=true
.\.venv\Scripts\python.exe scripts/test_system_browser.py
.\.venv\Scripts\python.exe scripts/test_camera_browser.py
.\.venv\Scripts\python.exe scripts/test_history_browser.py
.\.venv\Scripts\python.exe scripts/test_history_style_browser.py
.\.venv\Scripts\python.exe scripts/test_image_library_browser.py
```

日常仍可双击桌面“CraftEye 数智评鉴系统”或“启动焊接识别.bat”。开发测试可用 `launch.ps1 -Port 8516 -NoBrowser` 和 `stop.ps1 -Port 8516`，不占用正式网站的 8501 端口。
