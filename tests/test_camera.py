import asyncio
from fractions import Fraction
import threading
import unittest

import av
from PIL import Image

from camera import CameraProcessor


def frame(color='red'):
    value = av.VideoFrame.from_image(Image.new('RGB', (80, 60), color))
    value.pts, value.time_base = 100, Fraction(1, 90000)
    return value


class FakeRunner:
    def __init__(self):
        self.colors = []
        self.fail = False

    def infer(self, image, confidence):
        if self.fail:
            raise RuntimeError('test failure')
        self.colors.append(image.getpixel((0, 0)))
        return image.copy(), [{'类别': '缺陷', '置信度': confidence}]


class CameraTest(unittest.TestCase):
    def test_latest_frame_and_timestamps(self):
        runner = FakeRunner()
        processor = CameraProcessor(runner)
        output = asyncio.run(processor.recv_queued([frame('red'), frame('blue')]))
        self.assertEqual(runner.colors, [(0, 0, 255)])
        self.assertEqual(output[0].pts, 100)
        self.assertEqual(output[0].time_base, Fraction(1, 90000))
        result, error = processor.snapshot()
        self.assertIsNone(error)
        self.assertEqual(result.processed_frames, 1)
        result.rows[0]['类别'] = 'changed'
        self.assertEqual(processor.snapshot()[0].rows[0]['类别'], '缺陷')

    def test_threshold_change_invalidates_inflight_prediction(self):
        started, release = threading.Event(), threading.Event()

        class BlockingRunner(FakeRunner):
            def infer(self, image, confidence):
                started.set()
                if not release.wait(5):
                    raise TimeoutError('test synchronization timed out')
                return super().infer(image, confidence)

        processor = CameraProcessor(BlockingRunner())
        worker = threading.Thread(target=processor.recv, args=(frame(),))
        worker.start()
        self.assertTrue(started.wait(5))
        processor.configure(0.8)
        release.set()
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(processor.snapshot()[0])
        processor.recv(frame())
        self.assertEqual(processor.snapshot()[0].confidence, 0.8)

    def test_error_clears_previous_result_and_can_recover(self):
        runner = FakeRunner()
        processor = CameraProcessor(runner)
        processor.recv(frame())
        runner.fail = True
        processor.recv(frame())
        result, error = processor.snapshot()
        self.assertIsNone(result)
        self.assertIn('test failure', error)
        runner.fail = False
        processor.recv(frame())
        self.assertIsNone(processor.snapshot()[1])


if __name__ == '__main__':
    unittest.main()
