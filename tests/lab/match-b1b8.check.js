// Step 3a check: match graph shows B1–B8 with need/offer, routes = need × offer, crescent look, flow direction, no overlap.
// Serves public/ itself; needs Playwright via NODE_PATH. Usage: node match-b1b8.check.js <flag>
const http=require("http"),fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH to a node_modules that has playwright.");process.exit(2)}
const ROOT=path.resolve(__dirname,"..","..","public"),arg=process.argv[2]||"";
const MIME={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".json":"application/json"};
const srv=http.createServer((q,r)=>{const f=path.join(ROOT,decodeURIComponent(q.url.split("?")[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{"Content-Type":MIME[path.extname(f)]||"application/octet-stream"});r.end(d)}})});
const fail=m=>{console.error("FAIL "+m);process.exitCode=1};
function mock(){const f=path.join(ROOT,"tangle","kv-match-mock.js");if(!fs.existsSync(f))return null;const s=fs.readFileSync(f,"utf8");return JSON.parse(s.slice(s.indexOf("{"),s.lastIndexOf("}")+1))}
const M=mock(),IDS=M?Object.keys(M.projects):["48060125","15080750"],PAIRS=[];for(let i=0;i<IDS.length;i++)for(let j=i+1;j<IDS.length;j++)PAIRS.push([IDS[i],IDS[j]]);
const role=(pid,k)=>M.projects[pid].match[k].role;
const want=(a,b)=>{const out=[];for(const [x,y] of [[a,b],[b,a]])for(const k of Object.keys(M.keys))if(["need","both"].includes(role(x,k))&&["offer","both"].includes(role(y,k)))out.push(`${y}>${x}:${k}`);return out.sort()};
(async()=>{await new Promise(r=>srv.listen(0,"127.0.0.1",r));const port=srv.address().port,b=await chromium.launch();let n=0;
 const open=async(a,c,vp)=>{const p=await b.newPage({viewport:vp||{width:1100,height:740}});p._errs=[];p._ext=[];p.on("pageerror",e=>p._errs.push(e.message));p.on("request",r=>{if(!r.url().startsWith("http://127.0.0.1:"+port)&&!r.url().startsWith("data:"))p._ext.push(r.url())});
  await p.goto(`http://127.0.0.1:${port}/tangle/tangle-match.html?p=${a}&q=${c}`);await p.mouse.move(2,2);await p.waitForTimeout(2600);return p};
 const sats=p=>p.evaluate(()=>[...document.querySelectorAll("[data-kv-key]")].map(g=>({k:g.getAttribute("data-kv-key"),role:g.getAttribute("data-kv-role"),owner:g.getAttribute("data-kv-owner"),
   shadow:g.querySelector("[data-need-shadow]")?.getAttribute("data-need-shadow")||null,text:g.textContent})));
 if(!M){fail("kv-match-mock.js missing");}
 else if(arg==="--keys"){for(const [a,c] of PAIRS){const p=await open(a,c),S=await sats(p);
   for(const pid of [a,c]){const exp=Object.keys(M.keys).filter(k=>role(pid,k)!=="none").sort(),got=S.filter(s=>s.owner===pid).map(s=>s.k).sort();
    if(exp.join()!==got.join())fail(`${a}×${c} ${pid}: satellites ${got.join()} != ${exp.join()}`);
    for(const s of S.filter(s=>s.owner===pid))if(s.role!==role(pid,s.k))fail(`${a}×${c} ${pid} ${s.k}: role ${s.role} != ${role(pid,s.k)}`)}
   if(await p.evaluate(()=>document.querySelectorAll("[data-dd-satellite]").length!==document.querySelectorAll("[data-kv-key]").length))fail(`${a}×${c}: satellites without a B key (old topics?)`);
   n++;await p.close()}}
 else if(arg==="--routes"){for(const [a,c] of PAIRS){const p=await open(a,c);
   const got=(await p.evaluate(()=>TRACKS.filter(t=>!t.peer).map(t=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return`${f.pid}>${o.pid}:${t.tag}`}))).sort();
   if(got.join()!==want(a,c).join())fail(`${a}×${c}: routes [${got.join(" ")}] != expected [${want(a,c).join(" ")}]`);n++;await p.close()}}
 else if(arg==="--need-look"){for(const [a,c] of PAIRS){const p=await open(a,c),S=await sats(p),W=want(a,c);
   const expN=[a,c].reduce((t,pid)=>t+Object.keys(M.keys).filter(k=>role(pid,k)!=="none").length,0);if(S.length!==expN)fail(`${a}×${c}: ${S.length} B satellites, expected ${expN}`);
   for(const s of S){if(s.role==="both"){if(!s.text.includes("需要＋能提供"))fail(`${a}×${c} ${s.owner} ${s.k}: BOTH label`);continue}if(s.role==="offer"){if(s.shadow)fail(`${a}×${c} ${s.owner} ${s.k}: offer must not have a crescent shadow`);continue}
    const met=W.some(w=>w.endsWith(`>${s.owner}:${s.k}`));
    if(s.shadow!==(met?"met":"unmet"))fail(`${a}×${c} ${s.owner} ${s.k}: shadow ${s.shadow} != ${met?"met":"unmet"}`);
    if(met===s.text.includes("沒有對象"))fail(`${a}×${c} ${s.owner} ${s.k}: 沒有對象 text wrong (met=${met})`)}
   n++;await p.close()}}
 else if(arg==="--flow"){for(const [a,c] of PAIRS.filter(([a,c])=>want(a,c).length).slice(0,12)){const p=await open(a,c);
   // every complementary track carries 3 particles that move fast enough to see, from the offer end to the need end, teal -> warm
   const info=await p.evaluate(()=>({tracks:TRACKS.map((t,i)=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return{i,peer:!!t.peer,fromOffer:f.o.some(x=>x[0]===t.tag),toNeed:o.n.some(x=>x[0]===t.tag)}}),
     pts:PT.map(q=>({ti:q.ti,u:q.u})),col:typeof flowColor==="function"?[flowColor(0),flowColor(1)]:null}));
   const comp=info.tracks.filter(t=>!t.peer);
   if(!comp.length)fail(`${a}×${c}: no complementary tracks`);
   for(const t of comp){const n=info.pts.filter(q=>q.ti===t.i).length;if(n!==3)fail(`${a}×${c}: track ${t.i} has ${n} particles (want 3)`);if(!t.fromOffer||!t.toNeed)fail(`${a}×${c}: track ${t.i} must run offer -> need`)}
   if(info.pts.some(q=>info.tracks[q.ti]&&info.tracks[q.ti].peer))fail(`${a}×${c}: peer lines must not carry flow`);
   await p.waitForTimeout(1500);const s2=await p.evaluate(()=>PT.map(q=>({ti:q.ti,u:q.u})));
   info.pts.forEach((q,i)=>{const r=s2[i];if(!r)return;let du=r.u-q.u;if(du<0)du+=1;if(du<.2)fail(`${a}×${c}: particle ${i} moved only ${du.toFixed(3)} in 1.5s (want >= .2)`)});
   if(!info.col)fail(`${a}×${c}: flowColor(u) missing`);else{const [c0,c1]=info.col;if(!(c0[2]>c0[0]))fail(`${a}×${c}: flow should start teal at the offer end ${c0}`);if(!(c1[0]>c1[2]))fail(`${a}×${c}: flow should end warm at the need end ${c1}`)}
   n++;await p.close()}}
 else if(arg==="--pulse"){for(const [a,c] of PAIRS.filter(([a,c])=>want(a,c).length).slice(0,6)){const p=await open(a,c);
   // wait for at least one arrival: some met need shows a pulse, and later it fades back
   let seen=null;for(let k=0;k<40&&!seen;k++){seen=await p.evaluate(()=>{const g=[...document.querySelectorAll("[data-need-pulse]")].find(x=>+x.getAttribute("opacity")>.15);return g?g.closest("[data-kv-key]").getAttribute("data-kv-key"):null});if(!seen)await p.waitForTimeout(150)}
   if(!seen){fail(`${a}×${c}: no need pulse seen within 6s`);await p.close();continue}
   const role=await p.evaluate(k=>document.querySelector(`[data-need-pulse]`).closest("[data-kv-key]").getAttribute("data-kv-role"),seen);if(role!=="need"&&role!=="both")fail(`${a}×${c}: pulse on a non-need satellite (${role})`);
   n++;await p.close()}}
 else if(arg==="--peer"){for(const [a,c] of PAIRS){const p=await open(a,c);
   const exp=Object.keys(M.keys).filter(k=>role(a,k)==="offer"&&role(c,k)==="offer"&&!want(a,c).some(w=>w.endsWith(":"+k))).sort();
   const got=(await p.evaluate(()=>[...document.querySelectorAll("[data-kv-peer]")].map(x=>x.getAttribute("data-kv-peer")))).sort();
   if(got.join()!==exp.join())fail(`${a}×${c}: peer lines [${got.join()}] != both-offer [${exp.join()}]`);
   const dash=await p.evaluate(()=>[...document.querySelectorAll("[data-kv-peer]")].some(x=>x.getAttribute("stroke-dasharray")));if(dash)fail(`${a}×${c}: peer line is dashed`);
   const nn=Object.keys(M.keys).filter(k=>role(a,k)==="need"&&role(c,k)==="need");
   const bad=await p.evaluate(nn=>TRACKS.filter(t=>nn.includes(t.tag)&&!t.peer).length,nn);if(bad)fail(`${a}×${c}: need↔need connected`);
   const blocked=await p.evaluate(()=>{const out=[];document.querySelectorAll("[data-kv-peer]").forEach(pth=>{const tag=pth.getAttribute("data-kv-peer"),L=pth.getTotalLength(),m=pth.getScreenCTM();let hidden=0,tot=0;
     for(let k=2;k<=18;k++){const pt=pth.getPointAtLength(L*k/20),x=pt.x*m.a+m.e,y=pt.y*m.d+m.f,top=document.elementFromPoint(x,y);tot++;if(!top||!/兩邊都能提供/.test(top.getAttribute("aria-label")||""))hidden++}
     if(hidden/tot>.25)out.push(tag+" "+hidden+"/"+tot)});return out});
   if(blocked.length)fail(`${a}×${c}: peer line not clickable along its length: ${blocked.join(", ")}`);
   n++;await p.close()}}
 else if(arg==="--pair"){for(const [a,c] of PAIRS.filter(([a,c])=>want(a,c).length).slice(0,12)){const p=await open(a,c);
   const centre=(k,o)=>p.evaluate(([k,o])=>{const g=document.querySelector(`[data-kv-key="${k}"][data-kv-owner="${o}"]`);if(!g)return null;const r=g.querySelector("image").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}},[k,o]);
   const ring=()=>p.evaluate(()=>[...document.querySelectorAll("[data-kv-key] image")].map(i=>{const r=i.getBoundingClientRect();return[Math.round(r.x),Math.round(r.y)]}));
   const view=()=>p.evaluate(()=>({f:[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-focus")+":"+g.getAttribute("data-mf-role")),pts:typeof PT!=="undefined"?PT.length:0,
     dir:TRACKS.filter(t=>t.mf).map(t=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return f.o.some(x=>x[0]===t.tag)&&o.n.some(x=>x[0]===t.tag)}),back:getComputedStyle(document.getElementById("mfBack")).display!=="none"}));
   const W=want(a,c),tag=W[0].split(":")[1],needOwner=W[0].split(">")[1].split(":")[0];
   await p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerenter")));await p.waitForTimeout(300);
   const before=await ring(),pt=await centre(tag,needOwner);await p.mouse.click(pt.x,pt.y);await p.waitForTimeout(1200);let v=await view();
   if(v.f.sort().join()!==[tag+":need",tag+":offer"].sort().join())fail(`${a}×${c} ${tag}: walk-in shows ${v.f.join()}`);
   if(!v.back)fail(`${a}×${c}: no back button`);if(v.pts!==3||!v.dir.length||v.dir.some(x=>!x))fail(`${a}×${c}: pair flow wrong (particles ${v.pts}, offer→need ${v.dir})`);
   await p.locator("#mfBack").click();await p.waitForTimeout(1200);v=await view();const after=await ring();
   if(v.f.length||v.back)fail(`${a}×${c}: back did not leave`);if(after.length!==before.length||after.some((x,i)=>Math.hypot(x[0]-before[i][0],x[1]-before[i][1])>2))fail(`${a}×${c}: satellites not back in place`);
   // Esc also leaves
   const pt2=await centre(tag,needOwner);await p.mouse.click(pt2.x,pt2.y);await p.waitForTimeout(1200);await p.keyboard.press("Escape");await p.waitForTimeout(1200);v=await view();if(v.f.length)fail(`${a}×${c}: Esc did not leave`);
   // a satellite with no counterpart does not walk in
   const lone=await p.evaluate(()=>{const g=[...document.querySelectorAll("[data-kv-key]")].find(x=>x.querySelector('[data-need-shadow="unmet"]'));return g?[g.getAttribute("data-kv-key"),g.getAttribute("data-kv-owner")]:null});
   if(lone){const q=await centre(lone[0],lone[1]);await p.mouse.click(q.x,q.y);await p.waitForTimeout(900);v=await view();if(v.f.length)fail(`${a}×${c}: unmet need ${lone[0]} must not walk in`)}
   n++;await p.close()}}
 else if(arg==="--pair-peer"){const pairs=PAIRS.filter(([a,c])=>Object.keys(M.keys).some(k=>role(a,k)==="offer"&&role(c,k)==="offer"&&!want(a,c).some(w=>w.endsWith(":"+k)))).slice(0,8);for(const [a,c] of pairs){const p=await open(a,c);
   await p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerenter")));await p.waitForTimeout(300);
   const m=await p.evaluate(()=>{const pth=document.querySelector("[data-kv-peer]"),L=pth.getTotalLength(),pt=pth.getPointAtLength(L*.5),mm=pth.getScreenCTM();return{x:pt.x*mm.a+mm.e,y:pt.y*mm.d+mm.f,tag:pth.getAttribute("data-kv-peer")}});
   await p.mouse.click(m.x,m.y);await p.waitForTimeout(1200);
   const v=await p.evaluate(()=>({f:[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-role")),pts:PT.length,cap:(document.querySelector("[data-mf-caption]")||{}).textContent||""}));
   if(v.f.join()!=="offer,offer")fail(`${a}×${c} ${m.tag}: peer walk-in roles ${v.f.join()}`);if(v.pts!==0)fail(`${a}×${c}: peer walk-in must have no flow (${v.pts})`);if(!v.cap.includes("可聯合或交流"))fail(`${a}×${c}: caption ${v.cap}`);
   n++;await p.close()}}
 else if(arg==="--planet"){for(const [a,c] of PAIRS.slice(0,10)){const p=await open(a,c);
   await p.addInitScript(()=>{});await p.evaluate(()=>{window.__pm=[];const o=window.parent.postMessage.bind(window.parent);window.parent.postMessage=(m,t)=>{window.__pm.push(m);try{o(m,t)}catch(e){}}});
   const big=()=>p.evaluate(()=>[...document.querySelectorAll("#svg image")].map(i=>{const r=i.getBoundingClientRect();return{w:r.width,x:r.x+r.width/2,y:r.y+r.height/2}}).sort((x,y)=>y.w-x.w)[0]);
   let b0=await big();
   // a drag is not a click: no message
   await p.mouse.move(b0.x,b0.y);await p.mouse.down();for(let k=1;k<=8;k++){await p.mouse.move(b0.x+5*k,b0.y+3*k);await p.waitForTimeout(16)}await p.mouse.up();await p.waitForTimeout(500);
   let msgs=await p.evaluate(()=>window.__pm.filter(m=>m&&m.kind==="planet").length);if(msgs)fail(`${a}×${c}: dragging a planet sent a planet message`);
   await p.close();const q=await open(a,c);await q.evaluate(()=>{window.__pm=[];const o=window.parent.postMessage.bind(window.parent);window.parent.postMessage=(m,t)=>{window.__pm.push(m);try{o(m,t)}catch(e){}}});
   b0=await q.evaluate(()=>[...document.querySelectorAll("#svg image")].map(i=>{const r=i.getBoundingClientRect();return{w:r.width,x:r.x+r.width/2,y:r.y+r.height/2}}).sort((x,y)=>y.w-x.w)[0]);
   await q.mouse.click(b0.x,b0.y);await q.waitForTimeout(1500);
   const after=await q.evaluate(()=>({f:typeof focus!=="undefined"?focus:null,big:[...document.querySelectorAll("#svg image")].map(i=>{const r=i.getBoundingClientRect();return{w:r.width,x:r.x+r.width/2,y:r.y+r.height/2}}).sort((x,y)=>y.w-x.w)[0],msgs:window.__pm.filter(m=>m&&m.kind==="planet")}));
   const toC=Math.hypot(b0.x-550,b0.y-370)-Math.hypot(after.big.x-550,after.big.y-370);
   if(!(after.f&&after.big.w>b0.w*1.08&&toC>80))fail(`${a}×${c}: original planet focus did not happen (focus ${after.f}, ${b0.w.toFixed(0)}→${after.big.w.toFixed(0)}px, toward centre ${toC.toFixed(0)})`);
   if(after.msgs.length!==1)fail(`${a}×${c}: planet click must send exactly one planet message (${after.msgs.length})`);
   n++;await q.close()}}
 else if(arg==="--status"){for(const [a,c] of PAIRS){const p=await open(a,c);
   // the status pill on the graph = the rule from the data (standard v1.1), nothing filled yet; never RECOMMEND
   const N=r=>r==="need"||r==="both",O=r=>r==="offer"||r==="both",ks=Object.keys(M.keys);
   const comp=ks.some(k=>(N(role(a,k))&&O(role(c,k)))||(N(role(c,k))&&O(role(a,k)))),peer=ks.some(k=>role(a,k)==="offer"&&role(c,k)==="offer");
   const exp=comp?"CLARIFY_FIRST":peer?"EXPLORE":"ELIGIBLE";
   const got=await p.evaluate(()=>{const g=document.querySelector("[data-mf-status]");return g?{st:g.getAttribute("data-mf-status"),t:g.textContent}:null});
   const frame=await p.evaluate(()=>[...document.querySelectorAll("[data-mf-status] rect, [data-mf-status] circle, [data-mf-status] path")].some(e=>{const f=e.getAttribute("fill")||"",st=e.getAttribute("stroke")||"";return(f&&f!=="transparent"&&f!=="none")||(st&&st!=="none"&&st!=="transparent")}));
   if(frame)fail(`${a}×${c}: status must have no visible frame (yillkid 2026-11-15)`);
   if(!got)fail(`${a}×${c}: no status pill`);else{if(got.st!==exp)fail(`${a}×${c}: status ${got.st} != ${exp}`);if(/RECOMMEND|推薦/.test(got.st+got.t))fail(`${a}×${c}: RECOMMEND shown`)}
   // after the server reports EXPLORE (a supplement filled the minimum fields), the pill follows
   if(comp){await p.evaluate(()=>window.postMessage({type:"mf-status",status:"EXPLORE"},location.origin));}
   n++;await p.close()}}
 else if(arg==="--third"){for(const [a,c] of PAIRS){const p=await open(a,c);
   const ks=Object.keys(M.keys),exp=ks.filter(k=>role(a,k)==="need"&&role(c,k)==="need").sort();
   const got=(await p.evaluate(()=>[...document.querySelectorAll("[data-kv-third]")].map(x=>x.getAttribute("data-kv-third")))).sort();
   if(got.join()!==exp.join())fail(`${a}×${c}: third-party lines [${got.join()}] != both-need [${exp.join()}]`);
   if(await p.evaluate(()=>TRACKS.some(t=>!t.peer&&!t.mf&&document.querySelector(`[data-kv-third="${t.tag}"]`))))fail(`${a}×${c}: a both-need key got a flowing route`);
   n++;await p.close()}}
 else if(arg==="--multi"||arg==="--multi-focus"||arg==="--multi-pair"){
   // 3-plan sets (every 6th of 120) and 4-plan sets (every 21st of 210): deterministic sample
   const S3=[],S4=[];for(let i=0;i<IDS.length;i++)for(let j=i+1;j<IDS.length;j++)for(let k=j+1;k<IDS.length;k++){S3.push([IDS[i],IDS[j],IDS[k]]);for(let l=k+1;l<IDS.length;l++)S4.push([IDS[i],IDS[j],IDS[k],IDS[l]])}
   const sets=[...S3.filter((_,i)=>i%6===0),...S4.filter((_,i)=>i%21===0)];
   const openSet=async ps=>{const p=await b.newPage({viewport:{width:1100,height:740}});p._errs=[];p.on("pageerror",e=>p._errs.push(e.message));
    await p.addInitScript(()=>{window.__pm=[];const o=window.parent.postMessage.bind(window.parent);window.parent.postMessage=(m,t)=>{window.__pm.push(m);try{o(m,t)}catch(e){}}});
    await p.goto(`http://127.0.0.1:${port}/tangle/tangle-match.html?ps=${ps.join(",")}`);await p.mouse.move(2,2);await p.waitForTimeout(2600);return p};
   for(const ps of sets){const p=await openSet(ps);const tag=ps.length+"案 "+ps.join("×");
    const planets=await p.evaluate(()=>P.map(x=>x.pid));if(planets.join()!==ps.join()){fail(`${tag}: planets ${planets.join()}`);await p.close();continue}
    const expR=[];for(let i=0;i<ps.length;i++)for(let j=i+1;j<ps.length;j++)expR.push(...want(ps[i],ps[j]));
    if(arg==="--multi"){
     const got=(await p.evaluate(()=>TRACKS.filter(t=>!t.peer).map(t=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return`${f.pid}>${o.pid}:${t.tag}`}))).sort();
     if(got.join()!==expR.sort().join())fail(`${tag}: routes ${got.length} != expected ${expR.length}`);
     // layout: triangle / square
     const xy=await p.evaluate(()=>P.map(x=>[pos[x.id].x/Wd,pos[x.id].y/Hd]));const L=ps.length===3?[[.24,.32],[.76,.32],[.5,.78]]:[[.22,.30],[.78,.30],[.22,.76],[.78,.76]];
     if(xy.some((q,i)=>Math.hypot(q[0]-L[i][0],q[1]-L[i][1])>.03))fail(`${tag}: layout ${JSON.stringify(xy.map(q=>q.map(v=>+v.toFixed(2))))}`);
     const ov=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),X=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom,T=[...document.querySelectorAll("#svg text")].filter(t=>t.textContent.trim()).map(t=>[t.textContent,R(t)]),o=[];
      for(let i=0;i<T.length;i++)for(let j=i+1;j<T.length;j++)if(X(T[i][1],T[j][1]))o.push(T[i][0]+" × "+T[j][0]);for(const [t,r] of T)if(r.left<0||r.right>innerWidth||r.top<0||r.bottom>innerHeight)o.push(t+" clipped");return o});
     if(ov.length)fail(`${tag}: text overlap: ${ov.slice(0,2).join(" | ")}`);
     if(p._errs.length)fail(`${tag}: page errors ${p._errs.join(";")}`)}
    if(arg==="--multi-focus"){
     const idle=await p.evaluate(()=>({st:document.querySelectorAll("[data-mf-status]").length,third:document.querySelectorAll("[data-kv-third]").length,peer:document.querySelectorAll("[data-kv-peer]").length}));
     if(idle.st||idle.third||idle.peer)fail(`${tag}: not focused, but shows status ${idle.st} / third ${idle.third} / peer ${idle.peer}`);
     await p.evaluate(()=>{focus=P[0].id;syncMode();draw()});await p.waitForTimeout(400);
     const f=await p.evaluate(()=>({tr:TRACKS.filter(t=>!t.peer).map(t=>[P.find(x=>x.id===t.from).pid,P.find(x=>x.id===t.to).pid]),st:[...document.querySelectorAll("[data-mf-status]")].map(g=>[g.getAttribute("data-mf-pair"),g.getAttribute("data-mf-status")]),
       frame:[...document.querySelectorAll("[data-mf-status] rect")].some(r=>{const fl=r.getAttribute("fill")||"",sk=r.getAttribute("stroke")||"";return(fl&&fl!=="transparent")||(sk&&sk!=="none")})}));
     if(f.tr.some(([a,c])=>a!==ps[0]&&c!==ps[0]))fail(`${tag}: focused, but a route not touching the focused plan is drawn`);
     if(f.st.length!==ps.length-1)fail(`${tag}: focused, ${f.st.length} status labels (want ${ps.length-1})`);
     const N=r=>r==="need"||r==="both",O=r=>r==="offer"||r==="both",ks=Object.keys(M.keys);
     for(const [pair,st] of f.st){const [x,y]=pair.split("|");const comp=ks.some(k=>(N(role(x,k))&&O(role(y,k)))||(N(role(y,k))&&O(role(x,k)))),peer=ks.some(k=>role(x,k)==="offer"&&role(y,k)==="offer");
      const exp=comp?"CLARIFY_FIRST":peer?"EXPLORE":"ELIGIBLE";if(st!==exp)fail(`${tag}: status ${pair} ${st} != ${exp}`)}
     if(f.frame)fail(`${tag}: status has a visible frame`)}
    if(arg==="--multi-pair"&&expR.length){
     await p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerenter")));await p.waitForTimeout(200);
     const w=expR[0],[from,rest]=w.split(">"),[to,key]=rest.split(":");
     const c=await p.evaluate(([k,o])=>{const g=document.querySelector(`[data-kv-key="${k}"][data-kv-owner="${o}"]`);if(!g)return null;const r=g.querySelector("image").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}},[key,to]);
     if(!c){fail(`${tag}: satellite ${key}/${to} not found`);await p.close();continue}
     await p.mouse.click(c.x,c.y);await p.waitForTimeout(1200);
     const v=await p.evaluate(()=>({own:[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-owner")+":"+g.getAttribute("data-mf-role")).sort(),msg:window.__pm.filter(m=>m&&m.kind==="pair").pop()}));
     const okPair=v.own.some(x=>x.startsWith(to+":"))&&v.own.length===2;
     if(!okPair)fail(`${tag}: walk-in shows ${v.own.join()} (clicked ${key} of ${to})`);
     const partner=v.own.find(x=>!x.startsWith(to+":"));const pb=partner&&partner.split(":")[0];
     if(!v.msg||v.msg.pa!==to||v.msg.pb!==pb)fail(`${tag}: message pa/pb ${v.msg&&v.msg.pa}/${v.msg&&v.msg.pb} != ${to}/${pb}`);
     if(pb&&!want(to,pb).concat(want(pb,to)).some(x=>x.endsWith(":"+key)))fail(`${tag}: walked into ${to}×${pb} ${key}, which is not complementary`)}
    n++;await p.close()}}
 else if(arg==="--no-overlap"){for(const [a,c] of PAIRS)for(const vp of [{width:812,height:588},{width:1100,height:740}]){const p=await open(a,c,vp);
   const hits=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),X=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom,out=[];
    const T=[...document.querySelectorAll("#svg text")].filter(t=>t.textContent.trim()&&getComputedStyle(t).display!=="none"&&+(t.getAttribute("opacity")??1)>.05).map(t=>[t.textContent,R(t)]);
    for(const [t,r] of T)if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)out.push(t+" clipped");
    for(let i=0;i<T.length;i++)for(let j=i+1;j<T.length;j++)if(X(T[i][1],T[j][1]))out.push(T[i][0]+" × "+T[j][0]);
    const B=[...document.querySelectorAll("[data-kv-key] image")].map(i=>{const r=R(i);return{left:r.left+1,top:r.top+1,right:r.right-1,bottom:r.bottom-1}});
    for(const [t,r] of T)for(const bb of B)if(X(r,bb)){out.push(t+" covers a satellite");break}
    return [...new Set(out)]});
   if(hits.length)fail(`${a}×${c} @${vp.width}x${vp.height}: ${hits.slice(0,3).join(" | ")}`);await p.close()}n=PAIRS.length}
 else if(arg==="--hygiene"){for(const [a,c] of PAIRS.slice(0,10)){const p=await open(a,c);
   if(await p.evaluate(()=>document.querySelectorAll('[stroke-dasharray]:not([stroke-dasharray=""])').length))fail(`${a}×${c}: dashed lines`);
   if(p._errs.length)fail(`${a}×${c}: page errors ${p._errs.join(";")}`);if(p._ext.length)fail(`${a}×${c}: external requests ${p._ext.join(",")}`);n++;await p.close()}}
 else{console.error("flags: --keys | --routes | --need-look | --flow | --pulse | --peer | --pair | --pair-peer | --planet | --status | --third | --multi | --multi-focus | --multi-pair | --no-overlap | --hygiene");process.exitCode=2}
 await b.close();srv.close();if(!process.exitCode)console.log("OK",arg,n+" pairs")})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
