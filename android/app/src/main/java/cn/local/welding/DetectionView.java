package cn.local.welding;

import android.content.Context;
import android.graphics.*;
import android.view.View;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class DetectionView extends View {
    private Bitmap bitmap;
    private List<Detection> detections = Collections.emptyList();
    private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG | Paint.FILTER_BITMAP_FLAG);
    private final RectF imageBounds = new RectF();
    private static final int[] COLORS = {0xffdc2626,0xff16a34a,0xffd97706};
    public DetectionView(Context context) { super(context); setContentDescription("焊缝图片与检测框"); }
    public void setImage(Bitmap image, List<Detection> results) { bitmap=image; detections=results; invalidate(); }
    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (bitmap == null) {
            paint.setColor(0xff64748b); paint.setTextSize(16*getResources().getDisplayMetrics().scaledDensity);
            String text="选择一张焊接照片开始检测";
            canvas.drawText(text,(getWidth()-paint.measureText(text))/2,getHeight()/2,paint); return;
        }
        float scale=Math.min((float)getWidth()/bitmap.getWidth(),(float)getHeight()/bitmap.getHeight());
        float dx=(getWidth()-bitmap.getWidth()*scale)/2, dy=(getHeight()-bitmap.getHeight()*scale)/2;
        imageBounds.set(dx,dy,dx+bitmap.getWidth()*scale,dy+bitmap.getHeight()*scale);
        canvas.drawBitmap(bitmap,null,imageBounds,paint);
        float density=getResources().getDisplayMetrics().density;
        for (Detection d : detections) {
            float l=dx+d.left*scale, t=dy+d.top*scale, r=dx+d.right*scale, b=dy+d.bottom*scale;
            paint.setColor(COLORS[d.classId]); paint.setStyle(Paint.Style.STROKE); paint.setStrokeWidth(2*density);
            canvas.drawRect(l,t,r,b,paint); paint.setStyle(Paint.Style.FILL);
            paint.setTextSize(13*getResources().getDisplayMetrics().scaledDensity);
            String label=Detection.NAMES[d.classId]+String.format(Locale.CHINA," %.0f%%",d.confidence*100);
            float textWidth=paint.measureText(label)+8*density, textHeight=20*density;
            float labelX=Math.min(l,Math.max(0,getWidth()-textWidth)), labelY=Math.max(dy,t-textHeight);
            canvas.drawRect(labelX,labelY,labelX+textWidth,labelY+textHeight,paint);
            paint.setColor(Color.WHITE); canvas.drawText(label,labelX+4*density,labelY+15*density,paint);
        }
    }
}
