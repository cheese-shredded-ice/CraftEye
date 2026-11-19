"""Build a relocatable Windows runtime from the project's installed dependency closure."""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]
ROOT_PACKAGES = ['torch','torchvision','ultralytics','streamlit','streamlit-webrtc','requests']
LITE_PACKAGES = ['onnxruntime','opencv-python','streamlit','streamlit-webrtc','requests']
APP_FILES = ['app.py','advice.py','ai_analysis.py','ai_ui.py','camera.py','camera_ui.py',
             'common.py','dashboard_visuals.py','defect_references.py','focus_regions.py',
             'history_ui.py','image_library_ui.py','inference.py','recognition_history.py','score_ui.py',
             'scoring.py','teaching_report_ui.py','training_trends.py','workspace_ui.py','workspace.css']
APP_FILES += ['behavior_core.py','behavior_inference.py','behavior_video.py','behavior_ui.py']
APP_FILES += ['analysis_audit.py','engineering_ui.py','growth_chart.py']


def dependencies(roots=None):
    pending = [(name, frozenset()) for name in (roots or ROOT_PACKAGES)]
    packages, processed = {}, set()
    while pending:
        name, extras = pending.pop()
        name = canonicalize_name(name)
        if (name, extras) in processed:
            continue
        processed.add((name, extras))
        package = metadata.distribution(name)
        packages[name] = package
        for declaration in package.requires or []:
            requirement = Requirement(declaration)
            if not requirement.marker or any(requirement.marker.evaluate({'extra':extra}) for extra in {'', *extras}):
                pending.append((requirement.name, frozenset(requirement.extras)))
    return packages


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build(destination, lite=False):
    if destination.exists():
        raise RuntimeError(f'Destination already exists: {destination}')
    destination.mkdir(parents=True)
    runtime = destination/'runtime'
    runtime.mkdir()
    base = Path(sys.base_prefix)
    for name in ['python.exe','pythonw.exe','python3.dll','python313.dll',
                 'vcruntime140.dll','vcruntime140_1.dll','LICENSE.txt']:
        copy_file(base/name, runtime/name)
    ignore = shutil.ignore_patterns('site-packages','__pycache__','*.pyc','test','tests','idlelib','tkinter','ensurepip')
    shutil.copytree(base/'Lib',runtime/'Lib',ignore=ignore)
    shutil.copytree(base/'DLLs',runtime/'DLLs',ignore=shutil.ignore_patterns('*.pdb','_tkinter.pyd','tcl*','tk*'))
    # Isolate from installed Python versions, user-site directories and PYTHONPATH.
    (runtime/'python313._pth').write_text('.\nLib\nDLLs\nLib/site-packages\n..\nimport site\n',encoding='ascii')
    system = Path(os.environ['SystemRoot'])/'System32'
    for name in ['msvcp140.dll','msvcp140_1.dll','msvcp140_2.dll','msvcp140_atomic_wait.dll',
                 'msvcp140_codecvt_ids.dll','concrt140.dll','vcomp140.dll','libomp140.x86_64.dll']:
        if (system/name).is_file():
            copy_file(system/name,runtime/name)
    packages = dependencies(LITE_PACKAGES if lite else ROOT_PACKAGES)
    removed_bytes = 0
    for name, package in sorted(packages.items()):
        count = 0
        for entry in package.files or []:
            if '..' in entry.parts or '__pycache__' in entry.parts or entry.suffix == '.pyc':
                continue
            source = package.locate_file(entry)
            # Tests, C++ headers and source maps are not used by the shipped app.
            # Keep metadata and all licenses, including native-library notices.
            metadata_file = any(part.endswith(('.dist-info','.egg-info')) for part in entry.parts)
            if lite and not metadata_file and ('tests' in entry.parts or entry.suffix in {'.h','.hpp','.pxd','.pyx','.map'}):
                if source.is_file():
                    removed_bytes += source.stat().st_size
                continue
            if source.is_file():
                copy_file(source,runtime/'Lib/site-packages'/entry)
                count += 1
        print(f'{name}=={package.version}: {count} files',flush=True)
    for name in APP_FILES:
        copy_file(ROOT/name,destination/name)
    if lite:
        copy_file(ROOT/'onnx_backend.py',destination/'onnx_backend.py')
    for folder in ['assets','prompts']:
        shutil.copytree(ROOT/folder,destination/folder)
    # The existing lite runtime has no PyTorch/Ultralytics. It exposes a clear
    # missing-model message; full builds can run the optional behaviour module.
    if not lite and (ROOT/'models/behavior').is_dir():
        shutil.copytree(ROOT/'models/behavior', destination/'models/behavior',
                        ignore=shutil.ignore_patterns('__pycache__','*.download'))
    model_name = 'welding.onnx' if lite else 'welding.pt'
    for name in [model_name,'source.json','author-README.md']:
        copy_file(ROOT/'models'/name,destination/'models'/name)
    samples = sorted((ROOT/'dataset/test/images').glob('*.jpg'))
    # Include enough examples for first use; no training data download is needed.
    chosen = samples[::max(1,len(samples)//8)][:8]
    for sample in chosen:
        copy_file(sample,destination/'dataset/test/images'/sample.name)
    copy_file(ROOT/'.streamlit/config.toml',destination/'.streamlit/config.toml')
    (destination/'.streamlit/secrets.example.toml').write_text('DASHSCOPE_API_KEY = ""\n',encoding='utf-8')
    for name in ['launcher.py','使用说明.txt']:
        copy_file(ROOT/'packaging/windows'/name,destination/name)
    if lite:
        instructions=destination/'使用说明.txt'
        instructions.write_text(instructions.read_text(encoding='utf-8').replace('64 位便携版','64 位精简便携版（自带运行环境，无需下载）').replace('3GB 可用磁盘空间','1.5GB 可用磁盘空间')+
            '\n精简版使用同一训练权重导出的 ONNX 模型，以 CPU 推理运行；不包含训练组件。\n',encoding='utf-8')
        copy_file(ROOT/'outputs/portable-lite-check/model-parity.json',destination/'model-parity.json')
    for name,argument in [('启动网页.cmd',''),('停止网页.cmd',' --stop')]:
        # ASCII-only content works with the default Windows code page; paths use %~dp0.
        (destination/name).write_bytes(('@echo off\r\ncd /d "%~dp0"\r\n'
            'if not exist "%~dp0runtime\\pythonw.exe" (\r\n'
            '  echo Please extract the complete ZIP before starting.\r\n  pause\r\n  exit /b 1\r\n)\r\n'
            'start "" "%~dp0runtime\\pythonw.exe" -I -X utf8 "%~dp0launcher.py"'+argument+'\r\n').encode('ascii'))
    manifest = {'product':'CraftEye','version':'2.1','platform':'Windows x64','python':sys.version,
                'packages':{name:package.version for name,package in sorted(packages.items())},
                'edition':'lite' if lite else 'full', 'inference_backend':'ONNX Runtime CPU' if lite else 'PyTorch CPU',
                'trimmed_development_bytes':removed_bytes,
                'model_file':model_name,
                'model_sha256':hashlib.file_digest((destination/'models'/model_name).open('rb'),'sha256').hexdigest(),
                'api_key_included':False,'history_included':False,'sample_count':len(chosen)}
    (destination/'package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'BUILD COMPLETE {destination}',flush=True)


def archive(destination, include_api_key=False):
    target = destination.parent / (destination.name + '.zip')
    temporary = target.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True) as output:
        files=sorted(destination.rglob('*'))
        for source in files:
            if not source.is_file():
                continue
            relative=source.relative_to(destination)
            if relative.parts[0] in {'logs','outputs','.cache','.ultralytics','Ultralytics'} or '__pycache__' in relative.parts or source.suffix=='.pyc':
                continue
            if relative.as_posix()=='.streamlit/secrets.toml' and not include_api_key:
                raise RuntimeError('API key inclusion requires explicit --include-api-key authorization.')
            output.write(source,Path(destination.name)/relative)
    temporary.replace(target)
    digest=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
    target.with_suffix('.zip.sha256').write_text(digest+'  '+target.name+'\n',encoding='utf-8')
    print(f'ARCHIVE COMPLETE {target} ({target.stat().st_size/1024**2:.1f} MiB)',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/release/CraftEye-v2.1-Windows-x64')
    parser.add_argument('--archive-only',action='store_true')
    parser.add_argument('--lite',action='store_true')
    parser.add_argument('--include-api-key',action='store_true',help='Include an explicitly authorized preset secrets.toml when archiving.')
    args=parser.parse_args()
    if args.archive_only:
        archive(args.output.resolve(),include_api_key=args.include_api_key)
    else:
        build(args.output.resolve(),lite=args.lite)
