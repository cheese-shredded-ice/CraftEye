"""Curated teaching examples and recent recognition images with a local preview."""
import base64
from datetime import datetime
import io
import json
from pathlib import Path

from PIL import Image, ImageOps
import streamlit as st
from .common import ROOT
from .recognition_history import load_picker_records, load_picker_image, load_original_images

EXAMPLES = ROOT / 'assets' / 'weld-examples'


def catalog():
    examples = json.loads((EXAMPLES/'examples.json').read_text(encoding='utf-8'))
    options = {f'example:{item["id"]}': {'label':'示例 · '+item['label'], 'path':EXAMPLES/item['file']}
               for item in examples if (EXAMPLES/item['file']).is_file()}
    for record in load_picker_records():
        defects = json.loads(record['defects'])
        defect = defects[0].split('：',1)[0].split(':',1)[0][:16] if defects else '焊缝图片'
        try:
            date = datetime.fromisoformat(record['generated_at']).strftime('%m-%d %H:%M')
        except ValueError:
            date = record['generated_at'][:16]
        options['history:'+record['run_id']] = {
            'label':f'历史 #{record["display_sequence"]} · {date} · {defect}',
            'run_id':record['run_id'], 'original':bool(record['has_original'])}
    return options


def activate_source(kind):
    st.session_state['_image_source_kind'] = kind
    if kind == 'upload':
        st.session_state['image_library_choice'] = None


def select_picture(key):
    st.session_state['image_library_choice'] = key
    activate_source('library')


@st.cache_data(show_spinner=False)
def thumbnail_url(data):
    with Image.open(io.BytesIO(data)) as opened:
        image=ImageOps.exif_transpose(opened).convert('RGB')
        image.thumbnail((400,240))
        buffer=io.BytesIO()
        image.save(buffer,format='JPEG',quality=85)
    return 'data:image/jpeg;base64,'+base64.b64encode(buffer.getvalue()).decode('ascii')


def render_image_picker():
    upload=st.file_uploader('上传一张焊接图片',type=['jpg','jpeg','png','bmp','webp'],
        key='image_upload',on_change=activate_source,args=('upload',))
    options=catalog()
    if st.session_state.get('image_library_choice') not in options:
        st.session_state['image_library_choice']=None
    st.markdown('**示例和历史图片**')
    category=st.segmented_control('图片来源',['示例图片','历史图片'],default='示例图片',
        key='image_gallery_category',label_visibility='collapsed')
    prefix='history:' if category=='历史图片' else 'example:'
    keys=[key for key in options if key.startswith(prefix)]
    history=load_original_images([options[key]['run_id'] for key in keys if 'run_id' in options[key]])
    with st.container(key='image-gallery',height=300,border=False):
        for start in range(0,len(keys),2):
            columns=st.columns(2,gap='small')
            for column,key in zip(columns,keys[start:start+2]):
                item=options[key]
                data=item['path'].read_bytes() if 'path' in item else history.get(item['run_id'])
                with column:
                    if data:
                        label=item['label']
                        if 'run_id' in item:
                            label+=' · 原图'
                        active=st.session_state.get('_image_source_kind')=='library' and st.session_state.get('image_library_choice')==key
                        st.button(f'![{label}]({thumbnail_url(data)})',key='gallery_'+key,
                            help=label,type='primary' if active else 'secondary',
                            use_container_width=True,on_click=select_picture,args=(key,))
        if not keys:
            st.caption('暂无历史图片')
    selected=st.session_state.get('image_library_choice')
    source=None
    if st.session_state.get('_image_source_kind')=='upload':
        source=io.BytesIO(upload.getvalue()) if upload is not None else None
    elif selected:
        item=options[selected]
        if 'path' in item:
            source=item['path']
        else:
            data=load_picker_image(item['run_id'])
            source=io.BytesIO(data) if data else None
    return source
