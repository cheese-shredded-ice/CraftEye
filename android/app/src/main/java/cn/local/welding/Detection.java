package cn.local.welding;

public final class Detection {
    public static final String[] NAMES = {"焊接不良", "焊接良好", "缺陷"};
    public final int classId;
    public final float confidence, left, top, right, bottom;
    public Detection(int classId, float confidence, float left, float top, float right, float bottom) {
        this.classId = classId; this.confidence = confidence;
        this.left = left; this.top = top; this.right = right; this.bottom = bottom;
    }
}
