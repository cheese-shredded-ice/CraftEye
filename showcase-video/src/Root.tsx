import {Composition} from 'remotion';
import {Film, Brand, Shot} from './Film';
export const Root = () => <>
  <Composition id="CraftEye" component={Film} durationInFrames={2700} fps={30} width={1920} height={1080}/>
  <Composition id="Brand" component={Brand} durationInFrames={180} fps={30} width={1920} height={1080} defaultProps={{seconds:6,closing:false}}/>
  <Composition id="Result" component={Shot} durationInFrames={300} fps={30} width={1920} height={1080} defaultProps={{file:'crack.png',seconds:10}}/>
</>;
