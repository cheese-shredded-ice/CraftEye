import React from 'react';
import {AbsoluteFill, CanvasImage, Easing, Interactive, Track, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';

const ease = Easing.bezier(0.22, 1, 0.36, 1);
const clamp = {extrapolateLeft:'clamp', extrapolateRight:'clamp', easing:ease} as const;
const font = 'Microsoft YaHei, Segoe UI, sans-serif';

const Backdrop: React.FC = () => <AbsoluteFill style={{background:'radial-gradient(ellipse at 12% 20%, #116d7c 0%, #082c43 42%, #041520 100%)'}}>
  <div style={{position:'absolute',inset:0,opacity:.12,backgroundImage:'linear-gradient(#4be4dc33 1px,transparent 1px),linear-gradient(90deg,#4be4dc33 1px,transparent 1px)',backgroundSize:'80px 80px'}}/>
  <div style={{position:'absolute',width:1000,height:1000,border:'1px solid #50dbdc22',borderRadius:'50%',right:-400,top:-300}}/>
  <div style={{position:'absolute',width:1200,height:1200,border:'1px solid #50dbdc18',borderRadius:'50%',right:-500,top:-400}}/>
</AbsoluteFill>;

type BrandProps = {closing?:boolean; seconds:number};
const BrandInner:React.FC<BrandProps> = ({closing=false,seconds}) => {
  const frame=useCurrentFrame(); const {fps}=useVideoConfig();
  return <AbsoluteFill style={{fontFamily:font}}>
    <Backdrop/>
    <CanvasImage src={staticFile('welding.webp')} style={{position:'absolute',right:0,width:1100,height:1080,objectFit:'cover',opacity:.2}}/>
    <AbsoluteFill style={{alignItems:'center',justifyContent:'center',opacity:interpolate(frame,[0,.7*fps,(seconds-.5)*fps,seconds*fps],[0,1,1,0],clamp)}}>
      <div style={{padding:'34px 58px',background:'#effdff',borderRadius:32,boxShadow:'0 30px 100px #00111d88',scale:interpolate(frame,[0,seconds*fps],[.94,1.02],clamp)}}>
        <CanvasImage src={staticFile('logo.png')} style={{width:650,height:160,objectFit:'contain'}}/>
      </div>
      <h1 style={{color:'#f1fcff',fontSize:106,letterSpacing:12,fontWeight:700,margin:'50px 0 30px'}}>数智评鉴系统</h1>
      <div style={{height:3,width:interpolate(frame,[.5*fps,2*fps],[0,660],clamp),background:'linear-gradient(90deg,transparent,#4be5d5,transparent)'}}/>
      <div style={{marginTop:36,color:'#79b9ca',fontSize:28,letterSpacing:8}}>CraftEye · V2.1</div>
    </AbsoluteFill>
  </AbsoluteFill>;
};
export const Brand = Interactive.create({Component:BrandInner,layout:'absolute-fill'});

type ShotProps={file:string;seconds:number;crop?:[number,number,number,number];focus?:[number,number,number,number];pointer?:[number,number,number,number]};
const ShotInner:React.FC<ShotProps> = ({file,seconds,crop=[0,0,1920,1080],focus,pointer}) => {
  const frame=useCurrentFrame(); const {fps}=useVideoConfig();
  const [x,y,w,h]=crop;
  const fit=Math.min(1792/w,952/h);
  const cardWidth=w*fit,cardHeight=h*fit;
  const enter=interpolate(frame,[0,.6*fps],[0,1],clamp);
  return <AbsoluteFill style={{fontFamily:font}}>
    <Backdrop/>
    <div style={{position:'absolute',left:(1920-cardWidth)/2,top:(1080-cardHeight)/2,width:cardWidth,height:cardHeight,
      overflow:'hidden',borderRadius:24,boxShadow:'0 35px 100px #0007,0 0 0 1px #a4f6ff66',
      opacity:interpolate(frame,[0,.45*fps,(seconds-.35)*fps,seconds*fps],[0,1,1,0],clamp),
      translate:`0px ${interpolate(frame,[0,.8*fps],[20,0],clamp)}px`,
      scale:interpolate(frame,[0,seconds*fps],[.98,1.025],clamp)}}>
      <div style={{position:'absolute',left:-x*fit,top:-y*fit,width:1920,height:1080,scale:fit,transformOrigin:'top left'}}>
        <CanvasImage src={staticFile(file)} style={{width:1920,height:1080}}/>
        {focus && <div style={{position:'absolute',left:focus[0],top:focus[1],width:focus[2],height:focus[3],borderRadius:16,
          border:'4px solid #00d1bb',boxShadow:'0 0 0 9999px #001a3226,0 0 25px #00d1bb55',
          opacity:interpolate(frame,[1.3*fps,2.1*fps,(seconds-1)*fps,seconds*fps],[0,1,1,0],clamp)}}/>}
        {pointer && <div style={{position:'absolute',left:interpolate(frame,[.5*fps,2*fps],[pointer[0],pointer[2]],clamp),
          top:interpolate(frame,[.5*fps,2*fps],[pointer[1],pointer[3]],clamp),opacity:enter}}>
          <div style={{position:'absolute',left:-21,top:-21,width:56,height:56,borderRadius:'50%',background:'#00bfaa22',border:'2px solid #00bfaacc'}}/>
          <svg width="32" height="40" viewBox="0 0 32 40"><path d="M3 2v30l8-8 7 14 6-3-7-13h12z" fill="#fff" stroke="#164255" strokeWidth="2"/></svg>
        </div>}
      </div>
    </div>
  </AbsoluteFill>;
};
export const Shot=Interactive.create({Component:ShotInner,layout:'absolute-fill'});

export const Film:React.FC = () => {
  const {fps}=useVideoConfig();
  return <AbsoluteFill style={{background:'#041520'}}><Track name="展示视频 · 90秒">
    <Brand name="品牌开场" seconds={6} durationInFrames={6*fps}/>
    <Shot name="系统首页" file="home.png" seconds={8} from={6*fps} durationInFrames={8*fps} pointer={[900,560,170,270]}/>
    <Shot name="裂纹识别结果" file="crack.png" seconds={10} from={14*fps} durationInFrames={10*fps} focus={[32,575,548,185]}/>
    <Shot name="关键缺陷限分" file="crack.png" seconds={10} from={24*fps} durationInFrames={10*fps} crop={[625,243,1275,240]} focus={[934,419,650,40]}/>
    <Shot name="六维评价" file="crack.png" seconds={12} from={34*fps} durationInFrames={12*fps} crop={[625,472,1275,465]} focus={[1209,709,667,76]}/>
    <Shot name="改进建议与缺陷对照" file="advice.png" seconds={10} from={46*fps} durationInFrames={10*fps} crop={[638,251,1250,680]}/>
    <Shot name="优秀作品评价" file="excellent.png" seconds={10} from={56*fps} durationInFrames={10*fps}/>
    <Shot name="识别记录归档" file="history.png" seconds={10} from={66*fps} durationInFrames={10*fps} pointer={[1300,600,390,360]}/>
    <Shot name="训练成长曲线" file="history.png" seconds={8} from={76*fps} durationInFrames={8*fps} crop={[925,174,978,858]}/>
    <Brand name="品牌收尾" closing seconds={6} from={84*fps} durationInFrames={6*fps}/>
  </Track></AbsoluteFill>;
};
