"""Portable Windows launcher: owns one server, finds a free port, opens a browser."""
import argparse
import ctypes
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / 'logs'
STATE = LOGS / 'launcher.json'
STOP = LOGS / 'stop-request.json'


def notify(message):
    if sys.stdout:
        print(message, flush=True)
    else:
        ctypes.windll.user32.MessageBoxW(None, message, 'CraftEye 数智评鉴系统', 0x40)


def read_state():
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
        if state['root'] != str(ROOT) or not 8501 <= state['port'] <= 8599:
            return None
        return state
    except (OSError, ValueError, KeyError, TypeError):
        return None


def healthy(port):
    try:
        # Do not send localhost traffic through machine-wide proxy settings.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/_stcore/health', timeout=1) as response:
            return response.status == 200
    except Exception:
        return False


def free_port():
    for port in range(8501, 8600):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(('127.0.0.1', port))
            except OSError:
                continue
            return port
    raise RuntimeError('8501—8599 端口均被占用，请关闭部分程序后重试。')


def write_state(value):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(STATE)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    LOGS.mkdir(exist_ok=True)
    lock = (LOGS / 'launcher.lock').open('a+b')
    lock.seek(0, 2)
    if lock.tell() == 0:
        lock.write(b'0')
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        # The lock is held for the supervisor's lifetime; repeated clicks reuse it.
        for _ in range(180):
            state = read_state()
            if state and args.stop:
                STOP.write_text(json.dumps({'token': state['token']}), encoding='utf-8')
                return
            if state and healthy(state['port']):
                if not args.no_browser:
                    webbrowser.open(f'http://127.0.0.1:{state["port"]}')
                return
            time.sleep(.5)
        raise RuntimeError('启动仍未完成，请查看 logs 文件夹中的日志。')
    if args.stop:
        STATE.unlink(missing_ok=True)
        return
    STATE.unlink(missing_ok=True)
    STOP.unlink(missing_ok=True)
    python = ROOT / 'runtime/python.exe'
    if not python.is_file() or not any((ROOT / 'models' / name).is_file() for name in ('welding.pt','welding.onnx')):
        raise RuntimeError('文件不完整。请先完整解压安装包，再双击“启动网页.cmd”。')
    port = free_port()
    token = os.urandom(16).hex()
    env = os.environ.copy()
    # Keep runtime caches within the unpacked folder, not the build computer.
    env['PYTHONNOUSERSITE'] = '1'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONUTF8'] = '1'
    env['YOLO_CONFIG_DIR'] = str(ROOT / '.ultralytics')
    (ROOT / '.ultralytics').mkdir(exist_ok=True)
    env['YOLO_AUTOINSTALL'] = 'false'
    env['MPLCONFIGDIR'] = str(ROOT / '.cache/matplotlib')
    env['GIT_PYTHON_REFRESH'] = 'quiet'
    child = None
    try:
        with (LOGS / 'server.log').open('w', encoding='utf-8') as stdout, (LOGS / 'server-error.log').open('w', encoding='utf-8') as stderr:
            child = subprocess.Popen([str(python), '-I', '-B', '-X', 'utf8', '-m', 'streamlit', 'run', str(ROOT/'app.py'),
                '--server.address=127.0.0.1', f'--server.port={port}', '--server.headless=true',
                '--server.fileWatcherType=none', '--browser.gatherUsageStats=false'],
                cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                creationflags=subprocess.CREATE_NO_WINDOW)
            write_state({'root':str(ROOT),'port':port,'pid':child.pid,'token':token})
            for _ in range(180):
                if child.poll() is not None:
                    raise RuntimeError('网页服务启动失败，请查看 logs/server-error.log。')
                if healthy(port):
                    break
                time.sleep(.5)
            else:
                raise RuntimeError('网页启动超时，请查看 logs/server-error.log。')
            if not args.no_browser:
                webbrowser.open(f'http://127.0.0.1:{port}')
            elif sys.stdout:
                print(f'READY http://127.0.0.1:{port}', flush=True)
            while child.poll() is None:
                try:
                    if json.loads(STOP.read_text(encoding='utf-8')).get('token') == token:
                        break
                except (OSError, ValueError):
                    pass
                time.sleep(.5)
    finally:
        if child is not None and child.poll() is None:
            # Terminate only the Popen handle this launcher created.
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        STATE.unlink(missing_ok=True)
        STOP.unlink(missing_ok=True)
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        notify(str(error))
        raise SystemExit(1)
