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
const want=(a,b)=>{const out=[];for(const [x,y] of [[a,b],[b,a]])for(const k of Object.keys(M.keys))if(role(x,k)==="need"&&role(y,k)==="offer")out.push(`${y}>${x}:${k}`);return out.sort()};
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
   for(const s of S){if(s.role==="offer"){if(s.shadow)fail(`${a}×${c} ${s.owner} ${s.k}: offer must not have a crescent shadow`);continue}
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
   const role=await p.evaluate(k=>document.querySelector(`[data-need-pulse]`).closest("[data-kv-key]").getAttribute("data-kv-role"),seen);if(role!=="need")fail(`${a}×${c}: pulse on a non-need satellite`);
   n++;await p.close()}}
 else if(arg==="--peer"){for(const [a,c] of PAIRS){const p=await open(a,c);
   const exp=Object.keys(M.keys).filter(k=>role(a,k)==="offer"&&role(c,k)==="offer").sort();
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
 else{console.error("flags: --keys | --routes | --need-look | --flow | --pulse | --peer | --no-overlap | --hygiene");process.exitCode=2}
 await b.close();srv.close();if(!process.exitCode)console.log("OK",arg,n+" pairs")})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
