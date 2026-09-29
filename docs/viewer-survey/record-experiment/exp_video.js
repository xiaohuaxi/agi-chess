const {chromium}=require('playwright-core');
const exe=process.env.HOME+'/Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing';
(async()=>{
 const b=await chromium.launch({executablePath:exe,headless:true});
 const cfgs=[['v_dsf1_1080',{viewport:{width:1080,height:1920},deviceScaleFactor:1,recordVideo:{dir:'vid1',size:{width:1080,height:1920}}}],
             ['v_dsf2_540',{viewport:{width:540,height:960},deviceScaleFactor:2,recordVideo:{dir:'vid2',size:{width:1080,height:1920}}}],
             ['v_default',{viewport:{width:540,height:960},deviceScaleFactor:2,recordVideo:{dir:'vid3'}}]];
 for(const [name,o] of cfgs){
  const ctx=await b.newContext(o);const p=await ctx.newPage();
  await p.goto('file://'+process.cwd()+'/page.html');
  await p.waitForTimeout(500);
  for(let k=1;k<=3;k++){await p.evaluate(k=>applyMove(k),k);await p.waitForTimeout(1500);}
  const v=p.video();await ctx.close();console.log(name,await v.path());
 }
 await b.close();
})().catch(e=>{console.error(e);process.exit(1)});
