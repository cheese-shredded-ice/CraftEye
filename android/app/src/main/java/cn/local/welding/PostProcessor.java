package cn.local.welding;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** YOLOv8 [1,7,8400]: xywh and three class probabilities (no objectness). */
public final class PostProcessor {
    public static List<Detection> decode(float[][] output, float threshold,
            float scaleX, float scaleY, int padLeft, int padTop, int width, int height) {
        if (output.length != 7 || output[0].length != 8400) {
            throw new IllegalArgumentException("模型输出格式不匹配");
        }
        List<Detection> candidates = new ArrayList<>();
        for (int i = 0; i < output[0].length; i++) {
            int cls = 0;
            for (int c = 1; c < 3; c++) if (output[4+c][i] > output[4+cls][i]) cls = c;
            float score = output[4+cls][i];
            float cx = output[0][i], cy = output[1][i], w = output[2][i], h = output[3][i];
            if (!Float.isFinite(score) || score < threshold || !Float.isFinite(cx) || !Float.isFinite(cy)
                    || !Float.isFinite(w) || !Float.isFinite(h) || w <= 0 || h <= 0) continue;
            // NMS must run before clipping at the image border, matching Ultralytics.
            float l = (cx-w/2-padLeft)/scaleX, r = (cx+w/2-padLeft)/scaleX;
            float t = (cy-h/2-padTop)/scaleY, b = (cy+h/2-padTop)/scaleY;
            if (r > l && b > t) candidates.add(new Detection(cls, score, l, t, r, b));
        }
        candidates.sort(Comparator.comparingDouble((Detection d) -> d.confidence).reversed());
        List<Detection> selected = new ArrayList<>();
        for (Detection candidate : candidates) {
            boolean keep = true;
            for (Detection prior : selected) {
                if (candidate.classId == prior.classId && iou(candidate, prior) > 0.7f) { keep = false; break; }
            }
            if (keep) selected.add(candidate);
            if (selected.size() == 300) break;
        }
        List<Detection> clipped = new ArrayList<>();
        for (Detection d : selected) {
            float l=clamp(d.left,width),r=clamp(d.right,width),t=clamp(d.top,height),b=clamp(d.bottom,height);
            if(r>l && b>t) clipped.add(new Detection(d.classId,d.confidence,l,t,r,b));
        }
        return clipped;
    }
    private static float clamp(float value, int maximum) { return Math.max(0, Math.min(maximum, value)); }
    static float iou(Detection a, Detection b) {
        float intersection = Math.max(0, Math.min(a.right,b.right)-Math.max(a.left,b.left))
                * Math.max(0, Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
        float union = (a.right-a.left)*(a.bottom-a.top)+(b.right-b.left)*(b.bottom-b.top)-intersection;
        return union > 0 ? intersection/union : 0;
    }
}
