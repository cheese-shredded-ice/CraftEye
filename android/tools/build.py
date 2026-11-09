"""Reproducible local build; keep .signing for future APK updates."""
import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('D:/welding-android-tools')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dependencies', action='store_true')
    args = parser.parse_args()
    env = os.environ.copy()
    info = subprocess.run(['java', '-XshowSettings:properties', '-version'], capture_output=True, text=True, check=True)
    java_home = next(line.split('=', 1)[1].strip() for line in info.stderr.splitlines() if 'java.home =' in line)
    env['JAVA_HOME'] = java_home
    env['ANDROID_HOME'] = str(TOOLS / 'sdk')
    env['GRADLE_USER_HOME'] = str(TOOLS / 'gradle-cache')
    signing = ROOT / '.signing'
    signing.mkdir(exist_ok=True)
    password_file = signing / 'password.txt'
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(32), encoding='ascii')
    env['WELDING_KEY_PASSWORD'] = password_file.read_text().strip()
    key = signing / 'welding-release.jks'
    if not key.exists():
        subprocess.run([str(Path(java_home) / 'bin/keytool.exe'), '-genkeypair', '-keystore', str(key),
                        '-storepass:file', str(password_file), '-keypass:file', str(password_file),
                        '-alias', 'welding', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '10000',
                        '-dname', 'CN=Welding Inspector Local, OU=Local Application, O=Local, C=CN'], check=True)
    (ROOT / 'local.properties').write_text('sdk.dir=D:/welding-android-tools/sdk\n', encoding='utf-8')
    command = [str(TOOLS / 'gradle-8.9/bin/gradle.bat'), '--no-daemon', '--console=plain']
    command += ['-PweldingBuildRoot=' + (TOOLS / 'build').as_posix()]
    for protocol, proxy in urllib.request.getproxies().items():
        if protocol in ('http', 'https'):
            parsed = urllib.parse.urlparse(proxy)
            command.extend([f'-D{protocol}.proxyHost={parsed.hostname}', f'-D{protocol}.proxyPort={parsed.port or 80}'])
    if args.dependencies:
        command += [':app:dependencies', '--configuration', 'releaseRuntimeClasspath']
    else:
        command += [':app:assembleRelease', ':app:testReleaseUnitTest', ':app:lintRelease']
    try:
        subprocess.run(command, env=env, cwd=ROOT, check=True)
    finally:
        if not args.dependencies and (TOOLS / 'build/app').exists():
            shutil.copytree(TOOLS / 'build/app', ROOT / 'app/build', dirs_exist_ok=True)


if __name__ == '__main__':
    main()
