"""CPU-only YOLOv8 inference, matching the existing single-image preprocessing/NMS."""
import ast
import cv2
import numpy as np
import onnxruntime as ort

from .common import CLASS_NAMES


def preprocess(image):
    pixels = np.asarray(image.convert('RGB'))
    height, width = pixels.shape[:2]
    gain = min(640 / height, 640 / width)
    size = round(width * gain), round(height * gain)
    dw, dh = (640 - size[0]) % 32 / 2, (640 - size[1]) % 32 / 2
    if (width, height) != size:
        pixels = cv2.resize(pixels, size, interpolation=cv2.INTER_LINEAR)
    pixels = cv2.copyMakeBorder(pixels, round(dh-.1), round(dh+.1), round(dw-.1), round(dw+.1),
                                cv2.BORDER_CONSTANT, value=(114,114,114))
    return np.ascontiguousarray(pixels.transpose(2,0,1)[None], dtype=np.float32) / 255.0


def non_max_suppression(boxes, scores, classes, threshold=.7, maximum=300):
    order = np.argsort(-scores, kind='stable')[:30000]
    keep = []
    areas = np.maximum(0, boxes[:,2]-boxes[:,0]) * np.maximum(0, boxes[:,3]-boxes[:,1])
    while order.size and len(keep) < maximum:
        index = int(order[0])
        keep.append(index)
        other = order[1:]
        if not other.size:
            break
        intersection = np.maximum(0, np.minimum(boxes[index,2:],boxes[other,2:])-
                                    np.maximum(boxes[index,:2],boxes[other,:2])).prod(axis=1)
        union = areas[index] + areas[other] - intersection
        iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union>0)
        order = other[(classes[other]!=classes[index]) | (iou<=threshold)]
    return keep


def postprocess(output, input_shape, original_size, confidence):
    if output.ndim != 3 or output.shape[0] != 1 or output.shape[1] != 4+len(CLASS_NAMES):
        raise ValueError('Unsupported welding model output shape.')
    predictions = output[0].T
    classes = predictions[:,4:].argmax(axis=1)
    scores = predictions[np.arange(len(predictions)),4+classes]
    mask = scores > confidence
    predictions, scores, classes = predictions[mask], scores[mask], classes[mask]
    boxes = np.concatenate((predictions[:,:2]-predictions[:,2:4]/2,
                            predictions[:,:2]+predictions[:,2:4]/2), axis=1)
    keep = non_max_suppression(boxes,scores,classes)
    boxes, scores, classes = boxes[keep], scores[keep], classes[keep]
    width, height = original_size
    gain = min(input_shape[0]/height,input_shape[1]/width)
    pad_x = round((input_shape[1]-width*gain)/2-.1)
    pad_y = round((input_shape[0]-height*gain)/2-.1)
    boxes[:,[0,2]] -= pad_x
    boxes[:,[1,3]] -= pad_y
    boxes /= gain
    boxes[:,[0,2]] = np.clip(boxes[:,[0,2]],0,width)
    boxes[:,[1,3]] = np.clip(boxes[:,[1,3]],0,height)
    return [(int(cls), box.tolist(), float(score)) for cls,box,score in zip(classes,boxes,scores)]


class ONNXDetector:
    def __init__(self, path):
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(path),sess_options=options,providers=['CPUExecutionProvider'])
        metadata = self.session.get_modelmeta().custom_metadata_map
        names = ast.literal_eval(metadata.get('names','{}'))
        if names != dict(enumerate(CLASS_NAMES)):
            raise ValueError('Welding model class labels do not match the application.')
        if int(metadata.get('stride','0')) != 32:
            raise ValueError('Welding model stride must be 32.')
        self.input_name = self.session.get_inputs()[0].name

    def detect(self, image, confidence):
        if not 0 <= confidence <= 1:
            raise ValueError('Confidence must be between 0 and 1.')
        tensor = preprocess(image)
        output = self.session.run(None,{self.input_name:tensor})[0]
        return postprocess(output,tensor.shape[2:],image.size,confidence)
