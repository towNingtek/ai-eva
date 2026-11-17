// Usage: copy versions to /tmp/mv/<ver>/public (git archive <commit> public | tar -x -C /tmp/mv/<ver>), then: node tests/lab/motion-diff.cjs f2cebc8 now
// Motion inventory by pixels, not by code: for each version and page, sample frames and measure WHERE things move.
// Anything that moves in the baseline but not now = a lost micro-motion / small effect.
// Regions: planet(s), satellites, routes/flow (canvas), background stars, label text, status pill. Pointer outside (idle) and inside.
const http=require('http'),fs=require('fs'),path=require('path');const{chromium}=require('playwright');
const MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8'};
const serve=root=>http.createServer((q,r)=>{const f=path.join(root,decodeURIComponent(q.url.split('?')[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{'Content-Type':MIME[path.extname(f)]||'application/octet-stream'});r.end(d)}})});
const VERS=process.argv.slice(2);
(async()=>{const b=await chromium.launch();const report={};
 for(const v of VERS){const s=serve(`/tmp/mv/${v}/public`);await new Promise(r=>s.listen(0,'127.0.0.1',r));const U=`http://127.0.0.1:${s.address().port}`;
  for(const [kind,url] of [['law','/tangle/tangle-law.html?p=48060125'],['match','/tangle/tangle-match.html?p=85457156&q=15080750']]){
   const p=await b.newPage({viewport:{width:1100,height:740}});await p.goto(U+url);await p.waitForTimeout(3500);
   for(const ptr of ['out','in']){
    if(ptr==='out')await p.evaluate(()=>document.getElementById('svg').dispatchEvent(new PointerEvent('pointerleave')));
    else{await p.mouse.move(550,600);await p.evaluate(()=>document.getElementById('svg').dispatchEvent(new PointerEvent('pointerenter')))}
    await p.waitForTimeout(500);
    // element-level motion over 2.5s, sampled every 250ms: max displacement / opacity change per class of element
    const res=await p.evaluate(async()=>{const cls=el=>{const t=el.tagName;if(t==='image')return el.getBoundingClientRect().width>30?'planet':'satellite';
       if(t==='text')return el.closest('[data-mf-status]')?'status':'label';if(t==='circle'&&el.getAttribute('fill')==='#a5a5c0')return'star';
       if(t==='circle')return'glow/halo';if(t==='path')return'route';return null};
      const snap=()=>[...document.querySelectorAll('#svg *')].map(el=>{const c=cls(el);if(!c)return null;const r=el.getBoundingClientRect();return{c,x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,o:+(el.getAttribute('opacity')??1),fo:+(el.getAttribute('fill-opacity')??1)}}).filter(Boolean);
      const cv=document.querySelector('canvas'),ctx=cv&&cv.getContext('2d'),px=()=>{if(!ctx)return null;const d=ctx.getImageData(0,0,cv.width,cv.height).data;let n=0,sum=0;for(let i=3;i<d.length;i+=16){if(d[i]>8){n++;sum+=i}}return{n,sum}};
      const A=snap(),P0=px(),mv={},op={};let canvasChanges=0,prev=P0;
      for(let k=0;k<10;k++){await new Promise(r=>setTimeout(r,250));const B=snap(),P1=px();if(P1&&prev&&(P1.n!==prev.n||P1.sum!==prev.sum))canvasChanges++;prev=P1;
       if(B.length===A.length)B.forEach((e,i)=>{const a=A[i];if(a.c!==e.c)return;mv[e.c]=Math.max(mv[e.c]||0,Math.hypot(e.x-a.x,e.y-a.y));op[e.c]=Math.max(op[e.c]||0,Math.abs(e.o-a.o),Math.abs(e.fo-a.fo),Math.abs(e.w-a.w))})}
      const cnt={};A.forEach(e=>cnt[e.c]=(cnt[e.c]||0)+1);
      return{move:Object.fromEntries(Object.entries(mv).map(([k,x])=>[k,+x.toFixed(1)])),fade:Object.fromEntries(Object.entries(op).map(([k,x])=>[k,+x.toFixed(2)])),count:cnt,canvasFramesChanged:canvasChanges,sameCount:snap().length===A.length}});
    report[`${kind}|${ptr}|${v}`]=res}
   await p.close()}
  s.close()}
 await b.close();
 // print a compact comparison: for each page/pointer, each element class: baseline vs others
 for(const kind of ['law','match'])for(const ptr of ['out','in']){console.log(`\n=== ${kind}, pointer ${ptr} ===`);
  const classes=new Set();VERS.forEach(v=>{const r=report[`${kind}|${ptr}|${v}`];Object.keys(r.count).forEach(c=>classes.add(c))});
  console.log('class'.padEnd(12),VERS.map(v=>v.padEnd(26)).join(''));
  for(const c of classes)console.log(c.padEnd(12),VERS.map(v=>{const r=report[`${kind}|${ptr}|${v}`];return(`n${r.count[c]||0} mv${r.move[c]??'-'} fd${r.fade[c]??'-'}`).padEnd(26)}).join(''));
  console.log('canvas'.padEnd(12),VERS.map(v=>(`frames changed ${report[`${kind}|${ptr}|${v}`].canvasFramesChanged}/10`).padEnd(26)).join(''))}
})().catch(e=>{console.error(e.stack);process.exit(1)});
