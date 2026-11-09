package cn.local.welding;

import org.junit.Test;
import static org.junit.Assert.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class PostProcessorTest {
    private String resource(String name) throws Exception {
        try(InputStream input=getClass().getClassLoader().getResourceAsStream(name)){
            return new String(input.readAllBytes(),StandardCharsets.UTF_8);
        }
    }
    @Test public void matchesAuthorModelReference() throws Exception {
        float[][] output=new float[7][8400];
        try(DataInputStream input=new DataInputStream(getClass().getClassLoader().getResourceAsStream("model-output.bin"))){
            for(int c=0;c<7;c++)for(int i=0;i<8400;i++)output[c][i]=input.readFloat();
        }
        String[] geometry=resource("geometry.txt").split(",");
        List<Detection> actual=PostProcessor.decode(output,0.25f,Float.parseFloat(geometry[2]),Float.parseFloat(geometry[3]),
                Integer.parseInt(geometry[4]),Integer.parseInt(geometry[5]),Integer.parseInt(geometry[0]),Integer.parseInt(geometry[1]));
        String[] expected=resource("expected-boxes.csv").strip().split("\n");
        assertEquals(expected.length,actual.size());
        for(int i=0;i<expected.length;i++){
            String[] e=expected[i].split(",");Detection a=actual.get(i);
            assertEquals(Float.parseFloat(e[0]),a.left,0.1f);assertEquals(Float.parseFloat(e[1]),a.top,0.1f);
            assertEquals(Float.parseFloat(e[2]),a.right,0.1f);assertEquals(Float.parseFloat(e[3]),a.bottom,0.1f);
            assertEquals(Float.parseFloat(e[4]),a.confidence,0.00001f);assertEquals((int)Float.parseFloat(e[5]),a.classId);
        }
    }
    @Test public void nmsKeepsDifferentClassesAndSuppressesSameClass(){
        float[][] output=new float[7][8400];
        for(int i=0;i<3;i++){output[0][i]=320;output[1][i]=320;output[2][i]=100;output[3][i]=100;}
        output[4][0]=0.9f;output[4][1]=0.8f;output[5][2]=0.7f;
        List<Detection> boxes=PostProcessor.decode(output,0.25f,1,1,0,0,640,640);
        assertEquals(2,boxes.size());assertEquals(0,boxes.get(0).classId);assertEquals(1,boxes.get(1).classId);
    }
    @Test public void rejectsInvalidBoxesAndAppliesThreshold(){
        float[][] output=new float[7][8400];
        output[4][0]=Float.NaN;output[0][1]=100;output[1][1]=100;output[2][1]=50;output[3][1]=50;output[4][1]=0.2f;
        assertTrue(PostProcessor.decode(output,0.25f,1,1,0,0,640,640).isEmpty());
    }
    @Test public void suppressionUsesUnclippedBoxesAtImageBoundary(){
        float[][] output=new float[7][8400];
        output[0][0]=0;output[1][0]=100;output[2][0]=200;output[3][0]=100;output[4][0]=0.9f;
        output[0][1]=50;output[1][1]=100;output[2][1]=100;output[3][1]=100;output[4][1]=0.8f;
        List<Detection> boxes=PostProcessor.decode(output,0.25f,1,1,0,0,640,640);
        assertEquals(2,boxes.size());assertEquals(0,boxes.get(0).left,0);
    }
    @Test public void adviceDoesNotDiagnoseFromGoodOrAbsentDetection(){
        assertTrue(AdviceEngine.summary(false,true,false).contains("暂不建议"));
        assertTrue(AdviceEngine.summary(false,false,false).contains("不能据此"));
        assertTrue(AdviceEngine.summary(false,true,true).contains("异常现象"));
        assertTrue(AdviceEngine.summary(true,true,false).contains("不良"));
    }
}
