"""Apply a user-authorized preset without printing or storing it in source code."""
import argparse
import json
from pathlib import Path
import tomllib

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('package',type=Path)
    parser.add_argument('--source-secrets',type=Path,default=ROOT/'.streamlit/secrets.toml')
    args=parser.parse_args()
    package=args.package.resolve()
    manifest_path=package/'package-manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    secret=tomllib.loads(args.source_secrets.read_text(encoding='utf-8-sig'))['DASHSCOPE_API_KEY'].strip()
    if not secret:
        raise ValueError('Preset key is empty.')
    # JSON basic strings are compatible with TOML for this ASCII API key.
    (package/'.streamlit/secrets.toml').write_text('DASHSCOPE_API_KEY = '+json.dumps(secret)+'\n',encoding='utf-8')
    manifest['api_key_included']=True
    manifest['api_key_preset']='User-authorized existing local preset; value omitted from manifest.'
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    instructions=package/'使用说明.txt'
    text=instructions.read_text(encoding='utf-8')
    start=text.index('【综合分析】')
    end=text.index('【摄像头】',start)
    text=text[:start]+'''【综合分析】
本地图片检测无需联网。
已预设 API Key，无需手动填写即可使用综合分析、六维评分和建议。
综合分析需要联网调用通义千问，调用费用计入预设密钥所属账号。
如需更换账号，可在右上角“设置”填写自己的 API Key；留空使用预设。
预设保存在 .streamlit/secrets.toml，随本安装包交付。
本包不包含本机私人识别记录，首次启动会自动载入随包附带的 60 条训练记录。

'''+text[end:]
    instructions.write_text(text,encoding='utf-8')
    print('Existing local API key preset applied. Secret value was not logged.')


if __name__=='__main__':main()
