"""Verify, collect, and archive the signed APK and corresponding source."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import zipfile
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT.parent/'安卓安装包'
BUILD_TOOLS=Path('D:/welding-android-tools/sdk/build-tools/35.0.0')


def main():
    OUTPUT.mkdir(exist_ok=True)
    apk=ROOT/'app/build/outputs/apk/release/app-release.apk'
    # Legacy Windows aapt cannot open Unicode paths; inspect an identical ASCII copy.
    inspection=BUILD_TOOLS.parents[2]/'verification/app-release.apk'
    inspection.parent.mkdir(exist_ok=True)
    shutil.copy2(apk,inspection)
    check=subprocess.run([str(BUILD_TOOLS/'apksigner.bat'),'verify','--verbose','--print-certs',str(inspection)],check=True,capture_output=True,text=True)
    align=subprocess.run([str(BUILD_TOOLS/'zipalign.exe'),'-c','-P','16','-v','4',str(inspection)],check=True,capture_output=True,text=True)
    badging=subprocess.run([str(BUILD_TOOLS/'aapt.exe'),'dump','badging',str(inspection)],check=True,capture_output=True)
    permissions=subprocess.run([str(BUILD_TOOLS/'aapt.exe'),'dump','permissions',str(inspection)],check=True,capture_output=True)
    assert b'android.permission.INTERNET' not in permissions.stdout
    assert b'arm64-v8a' in badging.stdout
    assert b'x86' not in badging.stdout
    tests=ET.parse(ROOT/'app/build/test-results/testReleaseUnitTest/TEST-cn.local.welding.PostProcessorTest.xml').getroot()
    assert tests.attrib['failures']=='0' and tests.attrib['errors']=='0'
    lint=ET.parse(ROOT/'app/build/reports/lint-results-release.xml').getroot()
    errors=[e.attrib for e in lint.findall('issue') if e.attrib.get('severity') in ('Error','Fatal')]
    assert not errors, errors
    with zipfile.ZipFile(apk) as z:
        assert hashlib.sha256(z.read('assets/welding.onnx')).hexdigest()=='dbddf8b39a4425b53aad2de279e0fb18b2189f97afdf9ad1c5a939cf59b29745'
        assert all(x.startswith('lib/arm64-v8a/') for x in z.namelist() if x.startswith('lib/') and x.endswith('.so'))
        for name in z.namelist():
            if name.endswith('.so'):
                binary=z.read(name)
                assert binary[:5]==b'\x7fELF\x02'
                phoff=struct.unpack_from('<Q',binary,32)[0]
                stride,count=struct.unpack_from('<HH',binary,54)
                for i in range(count):
                    header=struct.unpack_from('<IIQQQQQQ',binary,phoff+i*stride)
                    if header[0]==1:assert header[7]>=16384
    name='焊接识别-小米13-离线版-v1.0.0.apk'
    shutil.copy2(apk,OUTPUT/name)
    (OUTPUT/'APK签名验证.txt').write_text(check.stdout,encoding='utf-8')
    (OUTPUT/'APK信息.txt').write_bytes(badging.stdout+b'\n'+permissions.stdout)
    (OUTPUT/'SHA256.txt').write_text(hashlib.sha256(apk.read_bytes()).hexdigest()+'  '+name+'\n',encoding='utf-8')
    report={'package':'cn.local.welding','version':'1.0.0','min_android':'8.0','abi':'arm64-v8a',
            'apk_bytes':apk.stat().st_size,'signature_verified':True,'zip_alignment_16kb_verified':True,
            'network_permission':False,'onnx_asset_sha256_verified':True,
            'native_elf_alignment_16kb_verified':True,
            'java_unit_tests':int(tests.attrib['tests']),'test_failures':0,'lint_errors':0,
            'lint_warnings':sum(e.attrib.get('severity')=='Warning' for e in lint.findall('issue')),
            'device_tested':False,'model_comparison':json.loads((ROOT/'model-verification.json').read_text())}
    (OUTPUT/'验证报告.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    shutil.copy2(ROOT/'INSTALL.md',OUTPUT/'安装使用说明.md')
    shutil.copy2(ROOT/'THIRD_PARTY_NOTICES.md',OUTPUT/'第三方来源说明.md')
    with zipfile.ZipFile(OUTPUT/'焊接识别-Android源码-v1.0.0.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for file in ROOT.rglob('*'):
            relative=file.relative_to(ROOT)
            if not file.is_file() or set(relative.parts)&{'.signing','.gradle','build','logs','__pycache__'} or file.name=='local.properties':continue
            z.write(file,Path('WeldingInspector')/relative)
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
