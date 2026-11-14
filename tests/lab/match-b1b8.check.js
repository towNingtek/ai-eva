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
   const got=(await p.evaluate(()=>TRACKS.map(t=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return`${f.pid}>${o.pid}:${t.tag}`}))).sort();
   if(got.join()!==want(a,c).join())fail(`${a}×${c}: routes [${got.join(" ")}] != expected [${want(a,c).join(" ")}]`);n++;await p.close()}}
 else if(arg==="--need-look"){for(const [a,c] of PAIRS){const p=await open(a,c),S=await sats(p),W=want(a,c);
   const expN=[a,c].reduce((t,pid)=>t+Object.keys(M.keys).filter(k=>role(pid,k)!=="none").length,0);if(S.length!==expN)fail(`${a}×${c}: ${S.length} B satellites, expected ${expN}`);
   for(const s of S){if(s.role==="offer"){if(s.shadow)fail(`${a}×${c} ${s.owner} ${s.k}: offer must not have a crescent shadow`);continue}
    const met=W.some(w=>w.endsWith(`>${s.owner}:${s.k}`));
    if(s.shadow!==(met?"met":"unmet"))fail(`${a}×${c} ${s.owner} ${s.k}: shadow ${s.shadow} != ${met?"met":"unmet"}`);
    if(met===s.text.includes("沒有對象"))fail(`${a}×${c} ${s.owner} ${s.k}: 沒有對象 text wrong (met=${met})`)}
   n++;await p.close()}}
 else if(arg==="--flow"){for(const [a,c] of PAIRS.filter(([a,c])=>want(a,c).length).slice(0,12)){const p=await open(a,c);
   // particles advance along each track from A (offer end) to B (need end): u grows, and the head gets closer to B
   const s1=await p.evaluate(()=>PT.map(q=>({ti:q.ti,u:q.u})));await p.waitForTimeout(1500);const s2=await p.evaluate(()=>PT.map(q=>({ti:q.ti,u:q.u})));
   const ends=await p.evaluate(()=>TRACKS.map(t=>{const f=P.find(x=>x.id===t.from),o=P.find(x=>x.id===t.to);return{from:f.pid,to:o.pid,tag:t.tag,toRole:o.n.some(x=>x[0]===t.tag)?"need":"?",fromRole:f.o.some(x=>x[0]===t.tag)?"offer":"?"}}));
   if(!s1.length)fail(`${a}×${c}: no flow particles`);
   s1.forEach((q,i)=>{const r=s2[i];if(!r)return;let du=r.u-q.u;if(du<-.5)du+=1;if(!(du>0))fail(`${a}×${c}: particle on track ${q.ti} does not move forward`)});
   ends.forEach(e=>{if(e.fromRole!=="offer"||e.toRole!=="need")fail(`${a}×${c}: track ${e.tag} must start at the offer end and end at the need end`)});
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
 else{console.error("flags: --keys | --routes | --need-look | --flow | --no-overlap | --hygiene");process.exitCode=2}
 await b.close();srv.close();if(!process.exitCode)console.log("OK",arg,n+" pairs")})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
