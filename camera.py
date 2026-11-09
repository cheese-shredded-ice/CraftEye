"""WebRTC camera worker. No Streamlit calls are made on media threads."""
import copy
from dataclasses import dataclass
from datetime import datetime
import threading
import time

import av
from PIL import Image
from streamlit_webrtc import VideoProcessorBase


@dataclass(frozen=True)
class CameraResult:
    image: Image.Image
    original: Image.Image
    rows: list
    confidence: float
    timestamp: str
    completed_at: float
    elapsed_ms: float
    processed_frames: int


class CameraProcessor(VideoProcessorBase):
    def __init__(self, runner, confidence=0.25):
        self.runner = runner
        self._lock = threading.Lock()
        self._confidence = confidence
        self._revision = 0
        self._latest = None
        self._error = None
        self._count = 0

    def configure(self, confidence):
        with self._lock:
            if confidence != self._confidence:
                self._confidence = confidence
                self._revision += 1
                self._latest = None
                self._error = None

    def snapshot(self):
        with self._lock:
            # The PIL image is never mutated after publication. Copy table data.
            result = copy.copy(self._latest)
            if result is not None:
                result = CameraResult(result.image, result.original, copy.deepcopy(result.rows), result.confidence,
                    result.timestamp, result.completed_at, result.elapsed_ms, result.processed_frames)
            return result, self._error

    def recv(self, frame):
        with self._lock:
            confidence, revision = self._confidence, self._revision
        started = time.monotonic()
        try:
            image = Image.fromarray(frame.to_ndarray(format='rgb24'))
            image.thumbnail((960, 720), Image.Resampling.BILINEAR)
            annotated, rows = self.runner.infer(image, confidence)
            finished = time.monotonic()
            with self._lock:
                if revision != self._revision:
                    return frame  # Never publish predictions for an obsolete threshold.
                self._count += 1
                self._latest = CameraResult(annotated, image, rows, confidence,
                    datetime.now().astimezone().isoformat(timespec='seconds'), finished,
                    (finished-started)*1000, self._count)
                self._error = None
            output = av.VideoFrame.from_image(annotated)
            output.pts, output.time_base = frame.pts, frame.time_base
            return output
        except Exception as exc:
            with self._lock:
                if revision == self._revision:
                    self._latest = None
                    self._error = f'{type(exc).__name__}: {exc}'
            return frame

    async def recv_queued(self, frames):
        # Drop superseded input frames instead of letting inference lag behind.
        return [self.recv(frames[-1])]
