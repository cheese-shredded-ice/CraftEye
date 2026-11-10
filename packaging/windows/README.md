# Windows 便携发布

发布物：`outputs/release/CraftEye-v2.1-Windows-x64.zip`。

在当前已安装且验证过的环境中构建：

```powershell
.\.venv\Scripts\python.exe scripts/build_portable.py
.\.venv\Scripts\python.exe scripts/test_portable_browser.py outputs/release/CraftEye-v2.1-Windows-x64
.\.venv\Scripts\python.exe scripts/build_portable.py --archive-only
.\.venv\Scripts\python.exe scripts/verify_portable_archive.py
```

构建目标必须不存在，避免覆盖其他版本。依赖从当前 Python 环境解析，包括平台条件依赖和 extras；每个 distribution 的文件及许可证按 RECORD 复制，排除开发脚本、字节码和包目录之外的文件。应用采用文件白名单，密钥、识别历史、开发环境、视频制作工程及训练集不进入发布包。

运行时包含 Python 3.13 标准库、扩展库和应用依赖，通过 `_pth` 与 `-I` 隔离系统 Python、用户 site-packages 和 PYTHONPATH。按 Windows CPU 版打包，默认无需额外安装环境。

启动器使用文件锁避免重复服务；自动选择 8501—8599 空闲端口；健康检查成功后打开浏览器。后台启动器持有自己创建的服务进程句柄，停止操作通过随机令牌文件通知启动器，不按进程名称批量结束程序。迁移文件夹前请先停止服务。

验证涵盖隔离导入、真实模型推理、浏览器图片上传/下载、模拟摄像头截取、端口冲突、重复启动、停止，以及 ZIP 完整性和中文空格路径下的实际 CMD 入口。模拟摄像头需要开发测试生成的 `outputs/ai-check/fake-camera.y4m`。尚未在另一台物理电脑验证；使用 Windows 10/11 x64，建议 Edge/Chrome。

云端综合分析需要接收方配置自己的 API Key；验证不发起真实云端请求。

## 精简版

接收方依然无需安装或下载环境。发布包使用已训练权重导出的 FP32 ONNX 模型，保留动态矩形输入、RGB 归一化、按类别 NMS 和原坐标还原，与原 YOLOv8 单图推理一致。不附带 PyTorch、Ultralytics、SciPy、Polars、Matplotlib 等训练依赖；其余依赖去除测试文件、C++ 头文件和 JS source map，保留许可证及 metadata。

开发者构建命令（仅构建机需要安装导出工具）：

```powershell
.\.venv\Scripts\python.exe -m pip install -r packaging/windows/requirements-lite-build.txt
.\.venv\Scripts\python.exe scripts/export_portable_model.py
.\.venv\Scripts\python.exe scripts/verify_onnx_parity.py
.\.venv\Scripts\python.exe scripts/build_portable.py --lite --output outputs/release/CraftEye-v2.1-Lite-Windows-x64
.\.venv\Scripts\python.exe scripts/test_portable_browser.py outputs/release/CraftEye-v2.1-Lite-Windows-x64
.\.venv\Scripts\python.exe scripts/build_portable.py --archive-only --output outputs/release/CraftEye-v2.1-Lite-Windows-x64
.\.venv\Scripts\python.exe scripts/verify_portable_archive.py --lite
```

有 PT 权重的开发工程继续使用原推理实现；精简包只包含 ONNX 权重，自动使用轻量后端。`CRAFTEYE_TEST_APP_ROOT` 可将现有模拟综合分析测试服务指向精简包，用包内 Python 运行，验证评分、报告和记录组件没有因裁剪而失效。此变量仅被测试脚本读取。

离线启动测试拦截外部浏览器 HTTP 请求，并为服务设置不可用的外部 HTTP 代理；图片模型和摄像头不依赖下载。综合分析仍为原通义千问联网服务。

## 用户授权的密钥预设包

用户明确要求随包预设原密钥时，运行以下命令。默认构建仍不包含密钥；脚本仅从被 Git 忽略的本地配置读取，不在源码、日志或 manifest 中记录密钥值。预设版会更新使用说明和 manifest，覆盖同名 ZIP，校验文件同时更新。

```powershell
.\.venv\Scripts\python.exe scripts/preset_portable_key.py outputs/release/CraftEye-v2.1-Lite-Windows-x64
.\.venv\Scripts\python.exe scripts/build_portable.py --archive-only --include-api-key --output outputs/release/CraftEye-v2.1-Lite-Windows-x64
```

该版本的综合分析费用计入预设密钥所属账号。默认“不含密钥”的包检查不适用于该授权预设版本，应单独验证 ZIP 中的密钥与源配置一致、使用说明和 manifest 标记一致，以及网页空输入时正确选用本机预设。
