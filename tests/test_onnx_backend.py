import unittest
import numpy as np
from PIL import Image
from onnx_backend import preprocess, postprocess, non_max_suppression


class ONNXPostprocessTest(unittest.TestCase):
    def test_class_aware_nms_and_score_order(self):
        boxes=np.array([[0,0,100,100],[0,0,100,100],[0,0,100,100],[200,200,300,300]],dtype=np.float32)
        keep=non_max_suppression(boxes,np.array([.8,.9,.7,.6]),np.array([0,0,1,0]))
        self.assertEqual(keep,[1,2,3])

    def test_confidence_is_not_score_and_empty_predictions(self):
        output=np.zeros((1,7,2),dtype=np.float32)
        output[0,:4,0]=[320,160,128,64]
        output[0,4,0]=.75
        actual=postprocess(output,(320,640),(1280,640),.6)
        self.assertEqual(actual[0][0],0)
        self.assertEqual(actual[0][1],[512.,256.,768.,384.])
        self.assertEqual(actual[0][2],.75)
        self.assertEqual(postprocess(output,(320,640),(1280,640),.75),[])

    def test_portrait_and_landscape_preprocessing(self):
        for size in [(1920,1080),(480,640),(256,256),(1001,253)]:
            tensor=preprocess(Image.new('RGB',size,'red'))
            self.assertEqual(tensor.shape[:2],(1,3))
            self.assertTrue(all(d%32==0 and d<=640 for d in tensor.shape[2:]))
            self.assertEqual(tensor.dtype,np.float32)
            self.assertGreater(tensor[0,0].mean(),tensor[0,2].mean())


if __name__=='__main__':unittest.main()
