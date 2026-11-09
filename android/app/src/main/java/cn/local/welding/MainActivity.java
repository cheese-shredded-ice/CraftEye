package cn.local.welding;

import android.app.*;
import android.content.*;
import android.graphics.*;
import android.graphics.drawable.GradientDrawable;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

public final class MainActivity extends Activity {
    private static final int PICK_IMAGE=10, SAVE_REPORT=11;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private Detector detector;
    private AdviceEngine engine;
    private Bitmap image;
    private List<Detection> detections=Collections.emptyList();
    private boolean busy=true, hasResult=false;
    private boolean[] observations;
    private float threshold=0.25f;
    private long elapsed;
    private String sourceName="";
    private byte[] pendingExport;
    private TextView status, thresholdLabel, results, advice;
    private Button choose, sample, detect, observationsButton, export;
    private SeekBar thresholdBar;
    private ProgressBar progress;
    private DetectionView preview;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        try { engine=new AdviceEngine(this); observations=new boolean[engine.observations().length]; }
        catch(Exception e) { new AlertDialog.Builder(this).setMessage("建议文件加载失败，请重新安装应用").setPositiveButton("关闭",(d,w)->finish()).show(); return; }
        buildUi();
        worker.execute(()->{
            try {
                detector=new Detector(getApplicationContext());
                onUi(()->{busy=false;status.setText("模型已就绪 · 全程离线处理");updateControls();});
            } catch(Exception | OutOfMemoryError e) {
                onUi(()->{busy=false;status.setText("模型加载失败："+message(e)+"\n请检查手机剩余存储空间，关闭其他应用后重试。");updateControls();});
            }
        });
    }

    private void buildUi() {
        ScrollView scroll=new ScrollView(this); scroll.setFillViewport(true); scroll.setBackgroundColor(0xfff3f7f7);
        scroll.setFitsSystemWindows(true);
        LinearLayout root=new LinearLayout(this); root.setOrientation(LinearLayout.VERTICAL); root.setPadding(dp(20),dp(20),dp(20),dp(32));
        scroll.addView(root); setContentView(scroll);
        TextView title=text("焊接识别",28,0xff102b30); title.setTypeface(null,Typeface.BOLD); root.addView(title);
        root.addView(text("拍下焊缝，查看检测与改进建议",15,0xff52696d));
        status=text("首次启动，正在准备本地模型…",13,0xff0f766e); add(root,status,12);
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal); progress.setIndeterminate(true); add(root,progress,6);
        preview=new DetectionView(this); preview.setBackground(rounded(0xffe4eeee)); add(root,preview,16,280);
        LinearLayout selectRow=new LinearLayout(this); selectRow.setOrientation(LinearLayout.HORIZONTAL);
        choose=button("从相册选图",()->{
            Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT); intent.setType("image/*"); intent.addCategory(Intent.CATEGORY_OPENABLE);
            try { startActivityForResult(intent,PICK_IMAGE); } catch(ActivityNotFoundException e) { showError("手机没有可用的图片选择器"); }
        });
        sample=button("试用示例",()->loadImage(null));
        selectRow.addView(choose,new LinearLayout.LayoutParams(0,dp(50),1));
        LinearLayout.LayoutParams sampleParams=new LinearLayout.LayoutParams(0,dp(50),1); sampleParams.leftMargin=dp(10); selectRow.addView(sample,sampleParams); add(root,selectRow,12);
        thresholdLabel=text("置信度阈值：25%",14,0xff334e53); add(root,thresholdLabel,16);
        thresholdBar=new SeekBar(this); thresholdBar.setMax(90); thresholdBar.setProgress(20); add(root,thresholdBar,0);
        thresholdBar.setContentDescription("检测置信度阈值，百分之五至百分之九十五");
        thresholdBar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onStartTrackingTouch(SeekBar bar){} public void onStopTrackingTouch(SeekBar bar){}
            public void onProgressChanged(SeekBar bar,int value,boolean user){
                threshold=(value+5)/100f; thresholdLabel.setText("置信度阈值："+(value+5)+"%");
                if(user && hasResult){clearResults();status.setText("阈值已修改，请重新检测");}
            }
        });
        detect=button("开始检测",this::runDetection); detect.setTextColor(Color.WHITE); detect.setBackground(rounded(0xff0d9488)); add(root,detect,8,52);
        results=text("选择照片或示例图片，点击开始检测。",15,0xff334e53); results.setTextIsSelectable(true); add(root,results,20);
        observationsButton=button("补充现场现象（可选）",this::selectObservations); add(root,observationsButton,12,50);
        TextView adviceTitle=text("可能原因与调整建议",20,0xff102b30); adviceTitle.setTypeface(null,Typeface.BOLD); add(root,adviceTitle,22);
        advice=text("完成检测后显示建议。模型只识别三类外观标签，不测量电流、焊枪角度或速度。",15,0xff334e53);
        advice.setLineSpacing(dp(4),1); advice.setTextIsSelectable(true); add(root,advice,10);
        export=button("保存检测结果与报告",this::chooseExport); add(root,export,18,52);
        TextView footer=text("YOLOv8s · 作者 avinashhm\n焊接不良 / 焊接良好 / 缺陷\n图片在手机内处理，不上传服务器。",12,0xff647b80); add(root,footer,24);
        Button about=button("模型来源与应用说明",()->new AlertDialog.Builder(this).setTitle("关于焊接识别 1.0.0")
            .setMessage("使用作者 avinashhm 的 welding-defect-yolov8-full-training / weights/best.onnx。\n\n模型版本：2cbc6dc08b74b6bab1ebafc59a3804e4bc43e517\n\n识别引擎：ONNX Runtime 1.24.3（CPU）。三类标签无法进一步确定裂纹、气孔或工艺原因。建议为条件式排查规则。\n\n原图按方向校正，并缩放到最长边不超过 1600 像素用于检测和显示；报告坐标对应该处理后图片。\n\n模型来源：https://huggingface.co/avinashhm/welding-defect-yolov8-full-training\n模型元数据声明 AGPL-3.0；运行库使用 MIT 许可。源码及第三方说明随安装包一同交付。")
            .setPositiveButton("知道了",null).show()); add(root,about,8);
        updateControls();
    }

    private void loadImage(Uri uri) {
        busy=true;clearResults(); status.setText("正在读取图片…"); updateControls();
        worker.execute(()->{
            try {
                Bitmap loaded=decodeImage(uri);
                onUi(()->{
                    Bitmap old=image;image=loaded;observations=new boolean[observations.length];sourceName=uri==null?"内置数据集示例":"用户选择的图片";
                    preview.setImage(image,Collections.emptyList());if(old!=null && old!=image)old.recycle();
                    busy=false;status.setText("图片已就绪 · "+image.getWidth()+" × "+image.getHeight());updateControls();
                });
            } catch(Exception | OutOfMemoryError e) {onUi(()->{busy=false;status.setText("图片读取失败，请选择有效的 JPG、PNG 或 WebP 图片");showError(message(e));updateControls();});}
        });
    }
    private InputStream openImage(Uri uri) throws IOException {
        InputStream stream=uri==null?getAssets().open("sample.jpg"):getContentResolver().openInputStream(uri);
        if(stream==null)throw new IOException("无法读取图片"); return stream;
    }
    private Bitmap decodeImage(Uri uri) throws IOException {
        BitmapFactory.Options options=new BitmapFactory.Options();options.inJustDecodeBounds=true;
        try(InputStream stream=openImage(uri)){BitmapFactory.decodeStream(stream,null,options);}
        if(options.outWidth<=0 || options.outHeight<=0)throw new IOException("图片格式无效");
        options.inSampleSize=1;
        while(Math.max(options.outWidth,options.outHeight)/options.inSampleSize>1600)options.inSampleSize*=2;
        options.inJustDecodeBounds=false;options.inPreferredConfig=Bitmap.Config.ARGB_8888;
        Bitmap decoded;
        try(InputStream stream=openImage(uri)){decoded=BitmapFactory.decodeStream(stream,null,options);}
        if(decoded==null)throw new IOException("图片解码失败");
        int orientation=1;
        try(InputStream stream=openImage(uri)){orientation=new ExifInterface(stream).getAttributeInt(ExifInterface.TAG_ORIENTATION,1);}
        catch(IOException ignored){} // PNG/WebP without readable EXIF uses the encoded orientation.
        Matrix transform=new Matrix();
        switch(orientation){
            case 2:transform.setScale(-1,1);break;
            case 3:transform.setRotate(180);break;
            case 4:transform.setScale(1,-1);break;
            case 5:transform.setRotate(90);transform.postScale(-1,1);break;
            case 6:transform.setRotate(90);break;
            case 7:transform.setRotate(-90);transform.postScale(-1,1);break;
            case 8:transform.setRotate(-90);break;
        }
        if(!transform.isIdentity()){
            Bitmap rotated=Bitmap.createBitmap(decoded,0,0,decoded.getWidth(),decoded.getHeight(),transform,true);
            if(rotated!=decoded)decoded.recycle();decoded=rotated;
        }
        return decoded;
    }
    private void runDetection(){
        if(image==null || detector==null || busy)return;
        busy=true;clearResults();status.setText("正在手机上检测，请稍候…");updateControls();
        Bitmap source=image;float selectedThreshold=threshold;
        worker.execute(()->{
            try{
                long start=System.nanoTime();List<Detection> found=detector.detect(source,selectedThreshold);long duration=(System.nanoTime()-start)/1000000;
                onUi(()->{detections=found;elapsed=duration;hasResult=true;busy=false;preview.setImage(image,found);
                    status.setText("检测完成 · "+String.format(Locale.CHINA,"%.2f 秒",elapsed/1000.0));renderResults();updateControls();});
            }catch(Exception | OutOfMemoryError e){onUi(()->{busy=false;status.setText("检测失败，请重试或选择较小的图片");showError(message(e));updateControls();});}
        });
    }
    private void clearResults(){hasResult=false;detections=Collections.emptyList();if(preview!=null)preview.setImage(image,detections);
        if(results!=null)results.setText("点击开始检测，生成当前图片的结果。");if(advice!=null)advice.setText("完成检测后显示建议。");if(export!=null)updateControls();}
    private void renderResults(){
        StringBuilder summary=new StringBuilder();
        if(detections.isEmpty())summary.append("当前阈值下未检出目标，不代表焊接合格。");
        else {summary.append("检出 ").append(detections.size()).append(" 个区域\n");
            for(int i=0;i<detections.size();i++){Detection d=detections.get(i);summary.append(i+1).append(". ").append(Detection.NAMES[d.classId]).append(String.format(Locale.CHINA,"  %.1f%%\n",d.confidence*100));}}
        results.setText(summary.toString().trim());
        try{advice.setText(AdviceEngine.text(engine.build(detections,observations)));}catch(JSONException e){showError("建议生成失败："+message(e));}
    }
    private void selectObservations(){
        try{boolean[] draft=observations.clone();
            new AlertDialog.Builder(this).setTitle("人工补充实际现象")
                .setMultiChoiceItems(engine.observations(),draft,(dialog,index,checked)->draft[index]=checked)
                .setPositiveButton("应用",(dialog,which)->{observations=draft;if(hasResult)renderResults();})
                .setNeutralButton("清空",(dialog,which)->{observations=new boolean[observations.length];if(hasResult)renderResults();})
                .setNegativeButton("取消",null).show();
        }catch(JSONException e){showError(message(e));}
    }
    private JSONObject report() throws JSONException {
        JSONObject report=new JSONObject();report.put("app_version","1.0.0");report.put("model_source","avinashhm/welding-defect-yolov8-full-training");
        report.put("model_revision","2cbc6dc08b74b6bab1ebafc59a3804e4bc43e517");report.put("source",sourceName);
        report.put("processed_width",image.getWidth());report.put("processed_height",image.getHeight());
        report.put("confidence_threshold",threshold);report.put("inference_ms",elapsed);
        JSONArray boxes=new JSONArray();for(Detection d:detections){JSONObject box=new JSONObject();box.put("class_id",d.classId);box.put("class_name",Detection.NAMES[d.classId]);box.put("confidence",d.confidence);
            box.put("xyxy",new JSONArray(new float[]{d.left,d.top,d.right,d.bottom}));boxes.put(box);}
        report.put("detections",boxes);report.put("advice",engine.build(detections,observations));return report;
    }
    private void chooseExport(){
        new AlertDialog.Builder(this).setTitle("保存到手机")
            .setItems(new String[]{"检测与建议报告（TXT）","完整检测数据（JSON）","带检测框的图片（PNG）"},(dialog,index)->{
                try{
                    String extension,mime;
                    if(index==2){Bitmap rendered=annotatedBitmap();ByteArrayOutputStream bytes=new ByteArrayOutputStream();rendered.compress(Bitmap.CompressFormat.PNG,100,bytes);rendered.recycle();pendingExport=bytes.toByteArray();extension="png";mime="image/png";}
                    else{JSONObject report=report();String data=index==1?report.toString(2):"焊接识别报告\n"+results.getText()+"\n\n"+AdviceEngine.text(report.getJSONObject("advice"));
                        pendingExport=data.getBytes(StandardCharsets.UTF_8);extension=index==1?"json":"txt";mime=index==1?"application/json":"text/plain";}
                    Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType(mime);
                    intent.putExtra(Intent.EXTRA_TITLE,"welding-"+new SimpleDateFormat("yyyyMMdd-HHmmss",Locale.US).format(new Date())+"."+extension);
                    startActivityForResult(intent,SAVE_REPORT);
                }catch(Exception | OutOfMemoryError e){pendingExport=null;showError("无法生成报告："+message(e));}
            }).show();
    }
    private Bitmap annotatedBitmap(){
        Bitmap output=image.copy(Bitmap.Config.ARGB_8888,true);Canvas canvas=new Canvas(output);Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        int[] colors={0xffdc2626,0xff16a34a,0xffd97706};float size=Math.max(16,image.getWidth()/40f);
        for(Detection d:detections){paint.setColor(colors[d.classId]);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(Math.max(2,image.getWidth()/250f));canvas.drawRect(d.left,d.top,d.right,d.bottom,paint);
            paint.setStyle(Paint.Style.FILL);paint.setTextSize(size);String text=Detection.NAMES[d.classId]+String.format(Locale.CHINA," %.0f%%",d.confidence*100);
            float x=Math.min(d.left,Math.max(0,image.getWidth()-paint.measureText(text)-6)),y=Math.max(size+4,d.top);
            canvas.drawRect(x,y-size-4,x+paint.measureText(text)+6,y+4,paint);paint.setColor(Color.WHITE);canvas.drawText(text,x+3,y,paint);}
        return output;
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==PICK_IMAGE && result==RESULT_OK && data!=null && data.getData()!=null)loadImage(data.getData());
        if(request==SAVE_REPORT){byte[] bytes=pendingExport;pendingExport=null;
            if(result==RESULT_OK && data!=null && data.getData()!=null && bytes!=null){Uri target=data.getData();
                worker.execute(()->{try(OutputStream output=getContentResolver().openOutputStream(target,"wt")){
                    if(output==null)throw new IOException("无法打开保存位置");output.write(bytes);onUi(()->Toast.makeText(this,"已保存",Toast.LENGTH_SHORT).show());
                }catch(Exception e){onUi(()->showError("保存失败："+message(e)));}});
            }
        }
    }
    private void updateControls(){choose.setEnabled(!busy);sample.setEnabled(!busy);detect.setEnabled(!busy && image!=null && detector!=null);
        thresholdBar.setEnabled(!busy);observationsButton.setEnabled(!busy && image!=null);export.setEnabled(!busy && hasResult);progress.setVisibility(busy?View.VISIBLE:View.GONE);}
    private void onUi(Runnable task){runOnUiThread(()->{if(!isFinishing() && !isDestroyed())task.run();});}
    private void showError(String message){new AlertDialog.Builder(this).setTitle("提示").setMessage(message).setPositiveButton("知道了",null).show();}
    private static String message(Throwable e){return e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();}
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String content,int size,int color){TextView view=new TextView(this);view.setText(content);view.setTextSize(size);view.setTextColor(color);return view;}
    private Button button(String label,Runnable action){Button button=new Button(this);button.setText(label);button.setAllCaps(false);button.setTextSize(15);button.setOnClickListener(v->action.run());return button;}
    private GradientDrawable rounded(int color){GradientDrawable shape=new GradientDrawable();shape.setColor(color);shape.setCornerRadius(dp(12));return shape;}
    private void add(LinearLayout root,View view,int top){add(root,view,top,LinearLayout.LayoutParams.WRAP_CONTENT);}
    private void add(LinearLayout root,View view,int top,int height){LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT,height<0?height:dp(height));params.topMargin=dp(top);root.addView(view,params);}
    @Override protected void onDestroy(){super.onDestroy();worker.execute(()->{if(detector!=null)try{detector.close();}catch(Exception ignored){}});worker.shutdown();}
}
