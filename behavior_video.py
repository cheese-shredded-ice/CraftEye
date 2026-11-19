"""Bounded background video analysis, persistent reports and WebRTC processor."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from fractions import Fraction
import copy
import json
from pathlib import Path
import threading
import time
import uuid

import av
import cv2
from PIL import Image
from streamlit_webrtc import VideoProcessorBase

from behavior_core import BehaviorAnalyzer, BehaviorConfig
from behavior_inference import annotate, get_behavior_runner

OUTPUT = Path(__file__).parent / 'outputs' / 'behavior'
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='behavior')


def inspect_video(path):
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError('无法读取视频，请使用 MP4、MOV、AVI 或 WebM。')
        fps, frames = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if fps <= 0 or frames <= 0:
            raise ValueError('视频缺少有效帧率或时长信息。')
        if frames/fps > 600:
            raise ValueError('单次支持最长 10 分钟视频，请分段分析。')
        ok, frame = cap.read()
        if not ok:
            raise ValueError('视频没有可解码画面。')
        return {'fps': fps, 'frames': int(frames), 'duration': frames/fps,
                'preview': Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))}
    finally:
        cap.release()


class VideoJob:
    def __init__(self, source, config, output_root=None, runner=None):
        self.source, self.config = Path(source), config
        self.root = Path(output_root or OUTPUT) / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.runner = runner
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.status, self.progress = 'queued', 0.
        self.error, self.latest, self.image = None, None, None
        self.future = None

    def start(self):
        self.future = POOL.submit(self.run)
        return self

    def snapshot(self):
        with self.lock:
            return {'status': self.status, 'progress': self.progress, 'error': self.error,
                    'report': copy.deepcopy(self.latest), 'image': self.image.copy() if self.image else None,
                    'root': self.root}

    def run(self):
        cap = writer = None
        try:
            with self.lock:
                self.status = 'running'
            info = inspect_video(self.source)
            runner = self.runner or get_behavior_runner()
            analyzer = BehaviorAnalyzer(self.config)
            cap = cv2.VideoCapture(str(self.source))
            stride = max(1, round(info['fps']/3))
            rate = Fraction(str(info['fps'])).limit_denominator(10000)/stride
            index, last_time, stream = 0, 0., None
            samples = []
            while True:
                if self.cancel.is_set():
                    with self.lock:
                        self.status = 'cancelled'
                    break
                ok, frame = cap.read()
                if not ok:
                    if index < info['frames']-max(2, info['fps']):
                        raise ValueError('视频解码提前中断，请检查文件是否完整。')
                    break
                if index % stride == 0:
                    timestamp = index/info['fps']
                    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    image.thumbnail((960, 720), Image.Resampling.LANCZOS)
                    detections = runner.detect(image)
                    report = analyzer.update(timestamp, detections['people'], detections['equipment'], detections['phones'], image.size)
                    painted = annotate(image, detections, report)
                    if writer is None:
                        writer = av.open(str(self.root/'annotated.mp4'), 'w', options={'movflags': '+faststart'})
                        stream = writer.add_stream('libx264', rate=rate)
                        stream.width, stream.height = image.width//2*2, image.height//2*2
                        stream.pix_fmt = 'yuv420p'
                        stream.options = {'crf': '24', 'preset': 'veryfast'}
                    video_frame = av.VideoFrame.from_image(painted.resize((stream.width, stream.height)))
                    for packet in stream.encode(video_frame):
                        writer.mux(packet)
                    samples.append({'timestamp': round(timestamp, 3), 'people': len(detections['people']),
                                    'elapsed_ms': detections['elapsed_ms'], **report['latest']})
                    with self.lock:
                        self.latest, self.image = report, painted
                        self.progress = min(.99, (index+1)/info['frames'])
                    last_time = timestamp
                index += 1
            if writer:
                for packet in stream.encode():
                    writer.mux(packet)
                writer.close()
                writer = None
            if self.cancel.is_set():
                return
            if not samples:
                raise ValueError('未获得有效视频画面。')
            report = analyzer.finish(min(info['duration'], index/info['fps']))
            report.update(source_name=self.source.name, video_seconds=info['duration'],
                          sample_fps=float(rate), sample_count=len(samples),
                          mean_inference_ms=round(sum(s['elapsed_ms'] for s in samples)/len(samples), 1),
                          annotated_video='annotated.mp4')
            (self.root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            (self.root/'samples.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2), encoding='utf-8')
            with self.lock:
                self.latest, self.progress, self.status = report, 1., 'done'
        except Exception as exc:
            with self.lock:
                self.status, self.error = 'error', f'{type(exc).__name__}: {exc}'
        finally:
            if cap:
                cap.release()
            if writer:
                writer.close()


class BehaviorCameraProcessor(VideoProcessorBase):
    def __init__(self, config, runner=None):
        self.config, self.runner = config, runner
        self.analyzer = BehaviorAnalyzer(config)
        self.lock = threading.Lock()
        self.latest = self.image = self.error = None
        self.started = self.last_sample = None
        self.finalized = False

    def recv(self, frame):
        # Use receipt time for live capture; do not count processing lag or stopped time.
        now = time.monotonic()
        with self.lock:
            if self.finalized:
                return frame
            if self.last_sample is not None and now-self.last_sample < 1/3:
                return frame
            self.last_sample = now
            if self.started is None:
                self.started = now
        try:
            image = Image.fromarray(frame.to_ndarray(format='rgb24'))
            image.thumbnail((960, 720), Image.Resampling.LANCZOS)
            detections = (self.runner or get_behavior_runner()).detect(image)
            with self.lock:
                if self.finalized:
                    return frame
                self.latest = self.analyzer.update(now-self.started, detections['people'], detections['equipment'], detections['phones'], image.size)
                self.image = annotate(image, detections, self.latest)
                self.error = None
                output = av.VideoFrame.from_image(self.image)
            output.pts, output.time_base = frame.pts, frame.time_base
            return output
        except Exception as exc:
            with self.lock:
                self.error = f'{type(exc).__name__}: {exc}'
            return frame

    async def recv_queued(self, frames):
        return [self.recv(frames[-1])]

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.latest), self.image.copy() if self.image else None, self.error

    def finish(self):
        with self.lock:
            if not self.finalized:
                self.latest = self.analyzer.finish()
                self.finalized = True
            return copy.deepcopy(self.latest)
