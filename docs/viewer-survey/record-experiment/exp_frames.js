const {chromium}=require('playwright-core');
const fs=require('fs');
const exe=process.env.HOME+'/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
const [W,H,out]=[+process.argv[2],+process.argv[3],process.argv[4]];
const FPS=30, ANIM_MS=600, HOLD_S=1.5;
(async()=>{
 const b=await chromium.launch({executablePath:exe,headless:true});
 const ctx=await b.newContext({viewport:{width:W/2,height:H/2},deviceScaleFactor:2});
 const p=await ctx.newPage();
 await p.goto('file://'+process.cwd()+'/page.html');
 await p.evaluate(()=>document.fonts.ready);
 fs.rmSync(out,{recursive:true,force:true});fs.mkdirSync(out,{recursive:true});
 let list=[],idx=0,t0=Date.now();
 const shot=async()=>{const f=`${out}/f${String(idx++).padStart(5,'0')}.png`;await p.screenshot({path:f});return f};
 // initial hold
 list.push([await shot(),1.0]);
 for(let k=1;k<=3;k++){
  await p.evaluate(k=>{applyMove(k);document.getAnimations().forEach(a=>a.pause())},k);
  const n=Math.round(ANIM_MS/1000*FPS);
  for(let i=0;i<=n;i++){
   await p.evaluate(ms=>{document.getAnimations().forEach(a=>{a.currentTime=ms})},i*1000/FPS);
   list.push([await shot(),1/FPS]);
  }
  await p.evaluate(()=>document.getAnimations().forEach(a=>a.finish()));
  list.push([await shot(),HOLD_S]); // hold: one image, long duration
 }
 console.log('frames',idx,'ms total',Date.now()-t0);
 fs.writeFileSync(out+'/list.txt',list.map(([f,d])=>`file '${require('path').basename(f)}'\nduration ${d.toFixed(4)}`).join('\n')+`\nfile '${require('path').basename(list[list.length-1][0])}'\n`);
 await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
