package cn.local.welding;

import android.content.Context;
import org.json.*;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

public final class AdviceEngine {
    private final JSONObject rules;
    public AdviceEngine(Context context) throws Exception {
        try (InputStream input=context.getAssets().open("advice.json")) {
            ByteArrayOutputStream bytes=new ByteArrayOutputStream(); byte[] buffer=new byte[4096]; int count;
            while ((count=input.read(buffer))!=-1) bytes.write(buffer,0,count);
            rules=new JSONObject(bytes.toString("UTF-8"));
        }
    }
    public String[] observations() throws JSONException {
        JSONArray items=rules.getJSONArray("items"); String[] names=new String[items.length()];
        for(int i=0;i<names.length;i++) names[i]=items.getJSONObject(i).getString("condition");
        return names;
    }
    public static String summary(boolean abnormal, boolean good, boolean manual) {
        if(abnormal) return "检测到焊接不良或缺陷区域，请对照实际现象排查。";
        if(manual) return "模型未报告不良或缺陷，但你补充了异常现象，请先核实这些现场现象。";
        if(good) return "检出区域被标记为焊接良好。暂不建议仅凭图片改变电流、角度或速度，仍需按工艺要求复核。";
        return "当前阈值下未检出目标，不能据此判断焊接合格。建议补拍清晰近照后再识别。";
    }
    public JSONObject build(List<Detection> detections, boolean[] selected) throws JSONException {
        boolean abnormal=false,good=false,manual=false;
        for(Detection d:detections) { if(d.classId==1) good=true; else abnormal=true; }
        for(boolean checked:selected) if(checked) manual=true;
        JSONArray recommendations=new JSONArray(), observations=new JSONArray();
        JSONArray items=rules.getJSONArray("items");
        for(int i=0;i<items.length();i++) {
            if(selected[i]) observations.put(items.getJSONObject(i).getString("condition"));
            if((manual && selected[i]) || (!manual && abnormal)) recommendations.put(items.getJSONObject(i));
        }
        JSONObject result=new JSONObject();
        result.put("summary",summary(abnormal,good,manual));
        result.put("basis",manual?"根据人工补充的现场现象筛选":"根据模型粗类别提供通用排查清单");
        result.put("manual_observations",observations);
        result.put("limitation",rules.getString("limitation"));
        result.put("recommendations",recommendations);
        result.put("method",recommendations.length()>0?rules.getString("method"):"可补充现场现象，查看对应排查建议。");
        return result;
    }
    public static String text(JSONObject report) throws JSONException {
        StringBuilder result=new StringBuilder(report.getString("summary"));
        result.append("\n\n").append(report.getString("limitation"));
        JSONArray items=report.getJSONArray("recommendations");
        if(items.length()>0) result.append("\n\n").append(report.getString("basis"));
        for(int i=0;i<items.length();i++) {
            JSONObject item=items.getJSONObject(i);
            result.append("\n\n").append(i+1).append(". ").append(item.getString("direction"));
            result.append("\n需核实的现象：").append(item.getString("condition"));
            result.append("\n可能原因：").append(item.getString("cause"));
            result.append("\n调整建议：").append(item.getString("action"));
        }
        result.append("\n\n").append(report.getString("method"));
        return result.toString();
    }
}
