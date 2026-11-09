# 焊接识别 Android

面向小米 13 的离线 ARM64 应用。最低 Android 8.0，目标 Android 15（API 35）。界面为原生 Java，推理采用 ONNX Runtime Android 1.24.3 的 CPU 执行器。

## 功能

- 从系统图片选择器读取照片，不申请整个相册或存储权限。
- 内置数据集示例，安装后可直接试用。
- 自动处理 EXIF 方向，最长边采样到不超过 1600 像素，以控制手机内存使用。
- 模型输入为 RGB、NCHW、640×640、归一化到 0–1；等比例缩放后用 114 灰色填充。
- 输出三类：焊接不良、焊接良好、缺陷。支持检测阈值 5%–95%，默认 25%；按类别执行 IoU 0.7 非极大值抑制。
- 展示检测框与置信度；可人工补充现场现象，筛选电流、速度、角度等排查建议。
- 通过系统文件保存器导出 PNG 检测图、TXT 建议说明、JSON 完整报告。报告坐标对应处理后图片。
- 无网络权限，模型和建议全部在手机内运行。未接入相机实时视频流。

## 模型

来源：<https://huggingface.co/avinashhm/welding-defect-yolov8-full-training>

固定版本 `2cbc6dc08b74b6bab1ebafc59a3804e4bc43e517`，作者文件 `weights/best.onnx`，不重新训练。

SHA256：`dbddf8b39a4425b53aad2de279e0fb18b2189f97afdf9ad1c5a939cf59b29745`

输入 `images: [1,3,640,640]`，输出 `output0: [1,7,8400]`。输出前四通道为 xywh，后三通道为类别概率，没有独立 objectness 通道。应用首次准备模型时验证 SHA256。

## 构建

本电脑工具位于 `D:\welding-android-tools`：Gradle 8.9、Android SDK platform 35、build tools 35.0.0、platform tools。JDK 为已有的 Java 17。

构建脚本将临时构建输出放到该工具目录的 `build/`，避免 Windows 上中文路径导致 JVM 测试类加载失败；完成后自动复制回项目 `app/build/`，源码仍保留在原目录。

在桌面“焊接识别”项目根目录执行：

```powershell
& 'D:\Python\python.exe' android\tools\prepare_build.py
& '.\.venv\Scripts\python.exe' android\tools\verify_model.py
& 'D:\Python\python.exe' android\tools\build.py
```

`verify_model.py` 需要电脑端的 PyTorch、Ultralytics、OpenCV 与 onnxruntime 1.24.3，用于交叉验证和更新 Java 测试样本。已有测试样本包含在源码中，重新打包时不必重新生成。

独立解压源码 ZIP 后，在解压的 `WeldingInspector` 目录内运行 `python tools/prepare_build.py` 和 `python tools/build.py` 即可使用已包含的模型与测试样本构建。脚本当前面向 Windows 并将 SDK 放在 D 盘；其他路径可修改两个脚本中的 `TOOLS` 常量和 SDK 配置。单独解压的源码不包含电脑端 PyTorch 数据集，因此不要直接运行 `verify_model.py`；交叉验证报告和 Java 测试输入已经包含在源码内。

Android Studio 可直接打开此目录。其他电脑需配置自己的 SDK 路径、JDK 17、Gradle 8.9 和签名参数。`build.py` 会为本地初次构建创建独立签名，并通过环境变量传递密码；保留本机 `.signing/` 文件夹才能给已安装的应用发布兼容更新。源码压缩包不含签名密钥。

执行的 Gradle 任务：`assembleRelease testReleaseUnitTest lintRelease`。APK 默认输出在 `app/build/outputs/apk/release/app-release.apk`。

## 验证边界

`model-verification.json` 记录作者 ONNX 与原始 PyTorch 权重在示例图片上的比对结果。Java 单元测试使用真实 ONNX 输出检查框坐标、类别和置信度，并检查同类框抑制、不同类别保留及建议分支。

构建、签名与静态检查不能替代小米 13 真机体验。安装后先点“试用示例”，再选自己的照片。手机实际耗时由 CPU 温度、系统调度和内存状态决定。

建议属于条件式工艺排查，模型不能从图片直接测出电流、角度、速度，也不能判断内部熔合或所有细分缺陷。
