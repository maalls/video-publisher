import puppeteer from 'puppeteer-core';import fs from 'fs';
const [,, N, outdir, startI, endI, html, vw, vh]=process.argv;
(async()=>{
 const b=await puppeteer.launch({executablePath:''+process.env.CHROMEBIN+'',headless:'new',defaultViewport:{width:+vw||540,height:+vh||960,deviceScaleFactor:+(process.env.DSF||2)},args:['--no-sandbox','--ignore-gpu-blocklist',...(process.env.GLARGS||'').split(' ').filter(Boolean)]});
 const p=await b.newPage();
 p.on('pageerror',e=>console.log('ERR',e.message));
 await p.goto('http://localhost:18765/'+(html||'video2.html')+'?y=-3400',{waitUntil:'load'});
 await p.waitForFunction('window.map&&map.loaded()&&document.getElementById("cnt").textContent.length>0',{timeout:60000});
 const n=+N, a=+startI||0, e=+endI||n;
 fs.mkdirSync(outdir,{recursive:true});
 const w0=Math.max(0,a-12);
 for(let i=w0;i<e;i++){
  const y=Math.round(-3400+i*(2024+3400)/(n-1)), warm=i<a;
  await p.evaluate(async (y,snap,warm)=>{const s=document.getElementById('t');s.value=y;s.dispatchEvent(new Event('input'));window.__anim(1/30,snap);if(!warm)await new Promise(r=>{map.once('idle',r);map.triggerRepaint()})},y,i===w0,warm);
  if(warm)continue;
  await new Promise(r=>setTimeout(r,60));
  await p.screenshot({path:`${outdir}/f${String(i).padStart(5,'0')}.jpg`,type:'jpeg',quality:90});
  if(i%50==0)console.log(i,y,new Date().toISOString());
 }
 await b.close();
})();
