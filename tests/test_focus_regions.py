import base64
import io
import unittest

from PIL import Image

from website.ai_analysis import make_payload
from website.focus_regions import MAX_FOCUS_CROPS, focus_regions


def row(confidence, box=(20, 20, 80, 80), label='缺陷'):
    return dict(zip(('置信度', '左', '上', '右', '下'), (confidence, *box)), 类别=label)


class FocusRegionsTest(unittest.TestCase):
    def test_strict_threshold_and_nested_boxes_remain(self):
        rows = [row(.60), row(.6001, (40, 40, 45, 60)), row(.94, (5, 5, 95, 95), '焊接不良'), row(.27)]
        regions = focus_regions(rows, (100, 100))
        self.assertEqual([item['detection_index'] for item in regions], [1, 2])
        self.assertEqual(regions[0]['crop_box'], [32, 32, 53, 68])

    def test_invalid_coordinates_and_scores_are_skipped_and_edges_clamped(self):
        rows = [row(True), row(float('nan')), row(1.1), row(.8, (80, 20, 10, 40)),
                row(.8, (110, 20, 150, 40)), row(.8, (0, 0, float('inf'), 40)), {'置信度': .9},
                row(.9, (-5, -4, 110, 120))]
        regions = focus_regions(rows, (100, 100))
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]['crop_box'], [0, 0, 100, 100])

    def test_payload_uses_clean_original_crops_not_drawn_annotations(self):
        original = Image.new('RGB', (100, 100), (20, 100, 40))
        annotated = Image.new('RGB', (100, 100), 'red')
        payload = make_payload(original, annotated, [row(.71), row(.27)], [], '', 'qwen3-vl-plus')
        content = payload['messages'][0]['content']
        images = [item['image_url']['url'] for item in content if item['type'] == 'image_url']
        self.assertEqual(len(images), 3)
        crop = Image.open(io.BytesIO(base64.b64decode(images[2].split(',')[1])))
        self.assertEqual(crop.size, (76, 76))
        pixel = crop.getpixel((10, 10))
        self.assertLess(pixel[0], 30)
        self.assertGreater(pixel[1], 90)
        self.assertIn('focus_regions', content[0]['text'])

    def test_no_focus_fallback_and_request_size_cap(self):
        image = Image.new('RGB', (100, 100))
        for rows, expected in (([row(.6)], 2), ([row(.9, (i, 0, i+10, 10)) for i in range(20)], MAX_FOCUS_CROPS+2)):
            payload = make_payload(image, image, rows, [], '', 'qwen3-vl-plus')
            content = payload['messages'][0]['content']
            self.assertEqual(sum(item['type'] == 'image_url' for item in content), expected)


if __name__ == '__main__':
    unittest.main()
