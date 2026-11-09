package cn.local.welding;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.Rect;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.FloatBuffer;
import java.security.MessageDigest;
import java.util.Collections;
import java.util.List;
import ai.onnxruntime.*;

public final class Detector implements AutoCloseable {
    private static final int SIZE = 640;
    private static final String HASH = "dbddf8b39a4425b53aad2de279e0fb18b2189f97afdf9ad1c5a939cf59b29745";
    private final OrtEnvironment environment;
    private final OrtSession session;
    private final String inputName;

    public Detector(Context context) throws Exception {
        File model = new File(context.getFilesDir(), "welding-v1.onnx");
        if (!model.exists() || !sha256(model).equals(HASH)) {
            File temp = new File(context.getFilesDir(), "welding.tmp");
            try (InputStream in = context.getAssets().open("welding.onnx"); FileOutputStream out = new FileOutputStream(temp)) {
                byte[] bytes = new byte[65536]; int count;
                while ((count = in.read(bytes)) != -1) out.write(bytes, 0, count);
            }
            if (!sha256(temp).equals(HASH)) throw new IllegalStateException("模型文件校验失败，请重新安装应用");
            if (!temp.renameTo(model)) throw new IllegalStateException("无法保存本地模型");
        }
        environment = OrtEnvironment.getEnvironment();
        try (OrtSession.SessionOptions options = new OrtSession.SessionOptions()) {
            options.setIntraOpNumThreads(Math.min(4, Math.max(1, Runtime.getRuntime().availableProcessors()/2)));
            options.setInterOpNumThreads(1);
            options.setOptimizationLevel(OrtSession.SessionOptions.OptLevel.ALL_OPT);
            session = environment.createSession(model.getAbsolutePath(), options);
        }
        inputName = session.getInputNames().iterator().next();
        long[] shape = ((TensorInfo)session.getInputInfo().get(inputName).getInfo()).getShape();
        if (shape.length != 4 || shape[0] != 1 || shape[1] != 3 || shape[2] != SIZE || shape[3] != SIZE) {
            session.close(); throw new IllegalStateException("模型输入尺寸不匹配");
        }
    }

    public List<Detection> detect(Bitmap source, float threshold) throws Exception {
        float scale = Math.min((float)SIZE/source.getWidth(), (float)SIZE/source.getHeight());
        int width = Math.round(source.getWidth()*scale), height = Math.round(source.getHeight()*scale);
        int left = (SIZE-width)/2, top = (SIZE-height)/2;
        Bitmap letterbox = Bitmap.createBitmap(SIZE, SIZE, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(letterbox);
        canvas.drawColor(Color.rgb(114,114,114));
        canvas.drawBitmap(source, null, new Rect(left, top, left+width, top+height), new Paint(Paint.FILTER_BITMAP_FLAG));
        int area = SIZE*SIZE;
        int[] pixels = new int[area];
        letterbox.getPixels(pixels, 0, SIZE, 0, 0, SIZE, SIZE);
        letterbox.recycle();
        float[] input = new float[area*3];
        for (int i=0; i<area; i++) {
            input[i] = ((pixels[i] >> 16)&255)/255f;
            input[area+i] = ((pixels[i] >> 8)&255)/255f;
            input[2*area+i] = (pixels[i]&255)/255f;
        }
        try (OnnxTensor tensor = OnnxTensor.createTensor(environment, FloatBuffer.wrap(input), new long[]{1,3,SIZE,SIZE});
             OrtSession.Result result = session.run(Collections.singletonMap(inputName, tensor))) {
            float[][][] output = (float[][][])result.get(0).getValue();
            return PostProcessor.decode(output[0], threshold, (float)width/source.getWidth(), (float)height/source.getHeight(),
                    left, top, source.getWidth(), source.getHeight());
        }
    }
    private static String sha256(File file) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        try (InputStream input = new FileInputStream(file)) {
            byte[] buffer = new byte[65536]; int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer,0,count);
        }
        StringBuilder hex = new StringBuilder();
        for (byte b : digest.digest()) hex.append(String.format("%02x", b));
        return hex.toString();
    }
    @Override public void close() throws OrtException { session.close(); }
}
