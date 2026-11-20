import unittest

from website.camera_ui import (
    CAMERA_CAPTURE_FRAME_TARGET,
    CAMERA_DEFAULT_RECOGNITION_MODE,
    camera_frame_progress,
)


class CameraRecognitionModeTest(unittest.TestCase):
    def test_default_mode_is_manual_capture(self):
        self.assertEqual(CAMERA_DEFAULT_RECOGNITION_MODE, '手动识别')


class CameraFrameProgressTest(unittest.TestCase):
    def test_counts_successful_frames_from_first_result(self):
        count, baseline = camera_frame_progress(1)
        self.assertEqual(count, 1)
        self.assertEqual(baseline, 0)

    def test_same_result_is_not_counted_twice(self):
        count, baseline = camera_frame_progress(4, 0)
        self.assertEqual(count, 4)
        count_again, same_baseline = camera_frame_progress(4, baseline)
        self.assertEqual(count_again, 4)
        self.assertEqual(same_baseline, baseline)

    def test_ten_frames_reach_capture_target(self):
        count, baseline = camera_frame_progress(CAMERA_CAPTURE_FRAME_TARGET, 0)
        self.assertEqual(count, CAMERA_CAPTURE_FRAME_TARGET)

    def test_nine_frames_do_not_reach_capture_target(self):
        count, _ = camera_frame_progress(CAMERA_CAPTURE_FRAME_TARGET - 1, 0)
        self.assertLess(count, CAMERA_CAPTURE_FRAME_TARGET)

    def test_progress_is_capped_at_target(self):
        count, _ = camera_frame_progress(25, 0)
        self.assertEqual(count, CAMERA_CAPTURE_FRAME_TARGET)

    def test_processor_restart_resets_baseline(self):
        count, baseline = camera_frame_progress(2, 9)
        self.assertEqual(count, 1)
        self.assertEqual(baseline, 1)


if __name__ == '__main__':
    unittest.main()
