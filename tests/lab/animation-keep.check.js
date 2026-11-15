// Animation preservation check: the 16 animations/interactions that existed in the accepted lab (f2cebc8, 2026-11-10) must still exist.
// Values may change (tuning is allowed); an animation dropping to zero / not present = FAIL (disappeared).
// Serves public/ (or ROOT env) itself; Playwright via NODE_PATH. Last line: "ALL KEPT 16" on success.
const http=require("http"),fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const ROOT=process.env.ROOT||path.resolve(__dirname,"..","..","public");
const MIME={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8"};
const srv=http.createServer((q,r)=>{const f=path.join(ROOT,decodeURIComponent(q.url.split("?")[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{"Content-Type":MIME[path.extname(f)]||"application/octet-stream"});r.end(d)}})});
const LAW="/tangle/tangle-law.html?p=48060125",MATCH="/tangle/tangle-match.html?p=48060125&q=15080750";
let kept=0;const lost=[];const check=(name,ok,detail)=>{console.log((ok?"kept ":"LOST ")+name.padEnd(22)+" "+detail);if(ok)kept++;else lost.push(name)};
// every animation frame: the largest image (planet) centre / size / effective opacity, and the zoom
const TRACE=()=>{window.__S=[];const t0=performance.now();const tick=()=>{const ims=[...document.querySelectorAll("#svg image")].sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width);
  const row={t:performance.now()-t0,vz:typeof VZ==="number"?VZ:1,b:[]};for(const im of ims.slice(0,2)){const r=im.getBoundingClientRect();let o=1,n=im;while(n&&n.id!=="svg"){o*=+(n.getAttribute&&n.getAttribute("opacity")||1);n=n.parentNode}row.b.push({x:r.x+r.width/2,y:r.y+r.height/2,w:r.width,o})}
  window.__S.push(row);if(performance.now()-t0<2600)requestAnimationFrame(tick)};requestAnimationFrame(tick)};
const at=(S,t)=>S.reduce((a,c)=>Math.abs(c.t-t)<Math.abs(a.t-t)?c:a);
const leave=p=>p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerleave")));
const enter=p=>p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerenter")));
const smallBodies=p=>p.evaluate(()=>[...document.querySelectorAll("#svg image")].filter(i=>i.getBoundingClientRect().width<30&&i.getBoundingClientRect().width>6).map(i=>{const r=i.getBoundingClientRect();return[r.x+r.width/2,r.y+r.height/2]}));
const allBodies=p=>p.evaluate(()=>[...document.querySelectorAll("#svg image")].map(i=>{const r=i.getBoundingClientRect();return{w:r.width,x:r.x+r.width/2,y:r.y+r.height/2}}).sort((a,b)=>b.w-a.w));
const maxMove=(a,b)=>a.length&&a.length===b.length?Math.max(...a.map((x,i)=>Math.hypot(x[0]-b[i][0],x[1]-b[i][1]))):0;
const stars=p=>p.evaluate(()=>[...document.querySelectorAll("#svg circle")].filter(c=>c.getAttribute("fill")==="#a5a5c0").slice(0,12).map(c=>+c.getAttribute("opacity")));
async function flowMoves(p){const n=await p.evaluate(()=>typeof PT!=="undefined"?PT.length:0);if(!n)return{n,du:0};const u0=await p.evaluate(()=>PT.map(q=>q.u));await p.waitForTimeout(1000);const u1=await p.evaluate(()=>PT.map(q=>q.u));
 const du=u0.reduce((t,x,i)=>{let d=(u1[i]??x)-x;if(d<0)d+=1;return t+d},0)/u0.length;return{n,du}}
async function drag(p,from,dx,dy){await p.mouse.move(from.x,from.y);await p.mouse.down();for(let k=1;k<=12;k++){await p.mouse.move(from.x+dx*k/12,from.y+dy*k/12);await p.waitForTimeout(16)}await p.mouse.up();await p.waitForTimeout(300)}
// how far one body moved on its own vs everything else (pan moves all; a real drag moves only that body)
function soloMove(before,after,idx){const t=before[idx],near=after.reduce((a,c)=>Math.hypot(c.x-t.x-60,c.y-t.y-40)<Math.hypot(a.x-t.x-60,a.y-t.y-40)?c:a);
 const ob=before.filter((_,i)=>i!==idx),oa=after.filter(c=>c!==near),n=Math.min(ob.length,oa.length);let sx=0,sy=0;for(let i=0;i<n;i++){sx+=oa[i].x-ob[i].x;sy+=oa[i].y-ob[i].y}
 const sh={x:sx/n,y:sy/n};return{solo:Math.hypot(near.x-t.x-sh.x,near.y-t.y-sh.y),pan:Math.hypot(sh.x,sh.y)}}
(async()=>{await new Promise(r=>srv.listen(0,"127.0.0.1",r));const U=`http://127.0.0.1:${srv.address().port}`,b=await chromium.launch();
 const open=async url=>{const p=await b.newPage({viewport:{width:1100,height:740}});await p.addInitScript(TRACE);await p.goto(U+url);await p.waitForTimeout(2800);return p};
 try{
  // ── law ──
  let p=await open(LAW);let S=await p.evaluate(()=>window.__S);const cx=550,cy=Math.round(at(S,2500).b[0].y);
  const eEnd=S[S.length-1].b[0],eUR=S.map(r=>r.b[0]).filter(b=>b&&b.x>cx+80&&b.y<cy-40&&b.o<.9&&b.o>.02);
  const e3=eUR[0]||at(S,300).b[0];
  check("法規出場",eUR.length>=2&&Math.hypot(eEnd.x-cx,eEnd.y-cy)<10&&eEnd.o>.99,
   `${eUR.length} frames up-right & translucent (e.g. (${Math.round(e3.x)},${Math.round(e3.y)}) opacity ${e3.o.toFixed(2)}); end (${Math.round(eEnd.x)},${Math.round(eEnd.y)}) opacity ${eEnd.o.toFixed(2)}`);
  await leave(p);await p.waitForTimeout(400);let a=await smallBodies(p),s0=await stars(p);await p.waitForTimeout(3000);let c=await smallBodies(p),s1=await stars(p);
  check("法規公轉",maxMove(a,c)>=10,`satellites ${maxMove(a,c).toFixed(1)}px / 3s`);
  check("法規星星閃爍",s0.some((x,i)=>Math.abs(x-s1[i])>.005),"star opacity changes");
  let f=await flowMoves(p);check("法規光流",f.n>0&&f.du>0,`${f.n} particles, mean advance ${f.du.toFixed(3)}/s`);
  await enter(p);await p.waitForTimeout(400);a=await smallBodies(p);await p.waitForTimeout(1500);c=await smallBodies(p);
  check("法規停轉",maxMove(a,c)<1,`satellites ${maxMove(a,c).toFixed(1)}px while pointer over`);
  await p.evaluate(()=>{if(typeof orbitPaused!=="undefined")orbitPaused=true});
  let B=await allBodies(p);await drag(p,B[0],60,40);let A=await allBodies(p);let m=soloMove(B,A,0);
  check("法規拖曳行星",m.pan>=50||m.solo>=50,`pan ${m.pan.toFixed(0)}px, alone ${m.solo.toFixed(0)}px`);
  await p.close();p=await open(LAW);await p.evaluate(()=>{if(typeof orbitPaused!=="undefined")orbitPaused=true});
  B=await allBodies(p);const si=B.findIndex(x=>x.w<30&&x.w>12);await drag(p,B[si],60,40);A=await allBodies(p);m=soloMove(B,A,si);
  check("法規拖曳衛星",m.solo>=50&&m.pan<5,`satellite alone ${m.solo.toFixed(0)}px, everything else ${m.pan.toFixed(0)}px`);
  var z0=await p.evaluate(()=>VZ);await p.mouse.move(550,370);await p.mouse.wheel(0,-300);await p.waitForTimeout(400);var z1=await p.evaluate(()=>VZ);
  check("法規滾輪縮放",z1>z0*1.2,`zoom ${z0.toFixed(2)}→${z1.toFixed(2)}`);
  await p.close();
  // ── match ──
  p=await open(MATCH);S=await p.evaluate(()=>window.__S);
  const sep=r=>r.b.length>1?Math.abs(r.b[0].x-r.b[1].x):0,two=S.filter(r=>r.b.length>1&&r.b[1].w>15),m3=two[0]||at(S,300),m12=S[S.length-1];
  check("媒合出場",two.length>=2&&m3.vz<1.05&&Math.abs(m12.vz-1.2)<.03&&sep(m3)<sep(m12)*.6,`zoom ${m3.vz.toFixed(2)}→${m12.vz.toFixed(2)}, planets apart ${sep(m3).toFixed(0)}→${sep(m12).toFixed(0)}px`);
  await leave(p);await p.waitForTimeout(400);let P0=(await allBodies(p))[0];await p.waitForTimeout(3000);
  const P1=(await allBodies(p)).filter(x=>x.w>20).reduce((a,c)=>Math.hypot(c.x-P0.x,c.y-P0.y)<Math.hypot(a.x-P0.x,a.y-P0.y)?c:a);const dP=Math.hypot(P1.x-P0.x,P1.y-P0.y);
  check("媒合行星微晃",dP>.5&&dP<40,`planet ${dP.toFixed(1)}px / 3s`);
  f=await flowMoves(p);check("媒合光流",f.n>0&&f.du>0,`${f.n} particles, mean advance ${f.du.toFixed(3)}/s`);
  await enter(p);await p.waitForTimeout(400);a=await smallBodies(p);await p.waitForTimeout(1500);c=await smallBodies(p);
  check("媒合停轉",maxMove(a,c)<1,`satellites ${maxMove(a,c).toFixed(1)}px while pointer over`);
  B=await allBodies(p);await drag(p,B[0],60,40);A=await allBodies(p);m=soloMove(B,A,0);
  check("媒合拖曳行星",m.solo>=10,`planet alone ${m.solo.toFixed(0)}px`);
  await p.close();p=await open(MATCH);
  // clicking a planet focuses it: it moves toward the centre and grows (existing f2cebc8 behaviour, must stay)
  B=await allBodies(p);const pl=B[0];await p.mouse.click(pl.x,pl.y);await p.waitForTimeout(1500);A=await allBodies(p);
  const foc=A.reduce((a,c)=>c.w>a.w?c:a);const toC=Math.hypot(pl.x-550,pl.y-370)-Math.hypot(foc.x-550,foc.y-370);
  check("媒合點行星聚焦",foc.w>pl.w*1.08&&toC>80,`planet ${pl.w.toFixed(0)}→${foc.w.toFixed(0)}px wide, moved ${toC.toFixed(0)}px toward the centre`);
  await p.close();p=await open(MATCH);
  z0=await p.evaluate(()=>VZ);await p.mouse.move(550,370);await p.mouse.wheel(0,-300);await p.waitForTimeout(400);z1=await p.evaluate(()=>VZ);
  check("媒合滾輪縮放",z1>z0*1.2,`zoom ${z0.toFixed(2)}→${z1.toFixed(2)}`);
  await p.close();
  // ── workspace slide (CSS declared in the overlay; measured live separately) ──
  const ov=fs.readFileSync(path.join(ROOT,"tangle-lab-overlay.js"),"utf8");
  check("工作區滑入／滑出",/transition:transform \.32s/.test(ov)&&/transition:padding-left \.32s/.test(ov),"overlay declares transform .32s + padding-left .32s");
 }finally{await b.close();srv.close()}
 if(lost.length){console.log("LOST "+lost.length+": "+lost.join("、"));process.exit(1)}console.log("ALL KEPT "+kept)})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
