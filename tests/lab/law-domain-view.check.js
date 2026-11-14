// Step 1 check: default (議題) view unchanged; 法領域 view shows 10 keys with mock states.
// Serves public/ itself; needs Playwright via NODE_PATH. Usage: node law-domain-view.check.js <flag>
const http=require("http"),fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH to a node_modules that has playwright.");process.exit(2)}
const ROOT=path.resolve(__dirname,"..","..","public"),BASE=path.join(__dirname,"law-default-baseline.json"),arg=process.argv[2]||"";
const DOMAINS=["農村再生","區域計畫","國土計畫","都市計畫","非都市土地使用管制","開發審議","環境影響評估","水土保持","農業發展","農地農用認定"];
const MIME={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".json":"application/json"};
const srv=http.createServer((q,r)=>{const f=path.join(ROOT,decodeURIComponent(q.url.split("?")[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{"Content-Type":MIME[path.extname(f)]||"application/octet-stream"});r.end(d)}})});
const fail=m=>{console.error("FAIL "+m);process.exitCode=1};
function projects(){const s=fs.readFileSync(path.join(ROOT,"tangle","data.js"),"utf8");return JSON.parse(s.slice(s.indexOf("const PROJECTS=")+15,s.lastIndexOf("]")+1))}
function mock(){const s=fs.readFileSync(path.join(ROOT,"tangle","kv-law-mock.js"),"utf8");return JSON.parse(s.slice(s.indexOf("{"),s.lastIndexOf("}")+1))}
const snap=p=>p.evaluate(()=>({rules:[...document.querySelectorAll("[data-rule]")].map(g=>({code:g.getAttribute("data-rule"),label:g.querySelector("text")?.textContent||""})),
  kv:[...document.querySelectorAll("[data-kv-key]")].map(g=>({key:g.getAttribute("data-kv-key"),state:g.getAttribute("data-kv-state")})),
  planet:document.querySelectorAll("[data-project-planet]").length,dash:document.querySelectorAll('[stroke-dasharray]:not([stroke-dasharray=""])').length,
  vz:typeof VZ==="number"?+VZ.toFixed(2):null,demo:!!document.querySelector("[data-kv-demo-note]")&&getComputedStyle(document.querySelector("[data-kv-demo-note]")).display!=="none"}));
(async()=>{await new Promise(r=>srv.listen(0,"127.0.0.1",r));const port=srv.address().port,b=await chromium.launch(),P=projects();let n=0;
 const open=async id=>{const p=await b.newPage({viewport:{width:1100,height:740}});p._errs=[];p._ext=[];p.on("pageerror",e=>p._errs.push(e.message));p.on("request",r=>{if(!r.url().startsWith("http://127.0.0.1:"+port)&&!r.url().startsWith("data:"))p._ext.push(r.url())});
  await p.goto(`http://127.0.0.1:${port}/tangle/tangle-law.html?p=${id}`);await p.waitForTimeout(2600);return p};
 const toDomain=async p=>{};
 if(arg==="--domain"){const M=mock();for(const pr of P){const p=await open(pr.id);const s=await snap(p),m=M.projects[pr.id]; if(await p.locator("[data-kv-view],#kvView").count())fail(pr.short+" obsolete switch remains");
   const core=s.kv.filter(k=>k.state!=="uncovered"),unc=s.kv.filter(k=>k.state==="uncovered");
   if(core.length!==10||core.map(k=>k.key).sort().join()!==[...DOMAINS].sort().join())fail(pr.short+" domain keys wrong: "+core.map(k=>k.key).join());
   for(const k of core)if(m.law[k.key].state!==k.state)fail(`${pr.short} ${k.key} state ${k.state} != mock ${m.law[k.key].state}`);
   if(unc.length!==m.uncovered.length||unc.map(k=>k.key).sort().join()!==[...m.uncovered].sort().join())fail(pr.short+" uncovered mismatch");
   if(s.rules.length)fail(pr.short+" topic satellites still visible in domain view");if(!s.demo)fail(pr.short+" demo note missing");if(s.planet!==1)fail(pr.short+" planet count "+s.planet);n++;await p.close()}}
 else if(arg==="--no-overlap"){for(const pr of P){for(const vp of [{width:812,height:588},{width:1100,height:740}]){const p=await open(pr.id);await p.setViewportSize(vp);await p.waitForTimeout(400);await toDomain(p);
   await p.evaluate(()=>{orbitPaused=true});const SPIN=await p.evaluate(()=>typeof KV_SPIN==="number"?KV_SPIN:.012);
   for(let step=0;step<12;step++){await p.evaluate(([st,sp])=>{orbitTime=st*(Math.PI*2/12)/sp;render()},[step,SPIN]);
   const hits=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),X=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom;const fixed=["#kvDemo","#zc"].map(s=>[s,R(document.querySelector(s))]);
     const U=g=>{const rs=[...g.querySelectorAll("text")].map(R);return{left:Math.min(...rs.map(r=>r.left)),top:Math.min(...rs.map(r=>r.top)),right:Math.max(...rs.map(r=>r.right)),bottom:Math.max(...rs.map(r=>r.bottom))}};const labels=[...document.querySelectorAll("[data-kv-key],[data-project-planet]")].map(g=>[g.getAttribute("data-kv-key")||"專案名稱",U(g)]);const out=[];
     for(const [t,r] of labels){for(const [s,f] of fixed)if(X(r,f))out.push(t+" × "+s);if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)out.push(t+" clipped")}
     for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++)if(X(labels[i][1],labels[j][1]))out.push(labels[i][0]+" × "+labels[j][0]);const NM=(()=>{const t=document.querySelector("[data-project-planet] text");if(!t)return null;const b=R(t);return{left:b.left-4,top:b.top-2,right:b.right+4,bottom:b.bottom+2}})();if(NM)for(const [t,r] of labels)if(t!=="專案名稱"&&X(r,NM))out.push(t+" × 專案名稱");const B=[...document.querySelectorAll("[data-kv-key],[data-project-planet]")].map(g=>{const im=g.querySelector("image,circle[stroke]");if(!im)return null;const r=R(im);return[g.getAttribute("data-kv-key")||"行星",{left:r.left+1,top:r.top+1,right:r.right-1,bottom:r.bottom-1}]}).filter(Boolean);for(const [t,r] of labels)for(const [bn,bb] of B)if(X(r,bb))out.push(t+" label covers "+bn+" body");const bodies=[...document.querySelectorAll("[data-kv-key]")].map(g=>{const b=R(g.querySelector("image,circle[stroke]")||g);return[g.getAttribute("data-kv-key"),b.left+b.width/2,b.top+b.height/2,Math.max(b.width,b.height)/2]});document.querySelectorAll('path[stroke^="url(#kv-route"]').forEach(pth=>{const L=pth.getTotalLength(),m=pth.getScreenCTM();const end=pth.getPointAtLength(L),ex=end.x*m.a+m.e,ey=end.y*m.d+m.f;for(let k=1;k<40;k++){const q=pth.getPointAtLength(L*k/40),x=q.x*m.a+m.e,y=q.y*m.d+m.f;for(const [name,bx,by,br] of bodies){if(Math.hypot(ex-bx,ey-by)<br+30)continue;if(Math.hypot(x-bx,y-by)<br+4){out.push("route crosses "+name);return}}}});return [...new Set(out)]});
    if(hits.length){fail(`${pr.short} @${vp.width}x${vp.height} angle ${step*30}°: ${hits.slice(0,4).join(" | ")}`);break}}await p.close()}n++}}
 else if(arg==="--motion"){const M=mock();for(const pr of P){const p=await open(pr.id),m=M.projects[pr.id];
   const leave=()=>p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerleave")));
   const pos=()=>p.evaluate(()=>[...document.querySelectorAll("[data-kv-key] image")].map(i=>{const r=i.getBoundingClientRect();return[r.x,r.y]}));
   const mv=(a,b)=>Math.max(...a.map((x,i)=>Math.hypot(x[0]-b[i][0],x[1]-b[i][1])));
   await leave();await p.waitForTimeout(300);let a=await pos();await p.waitForTimeout(3000);let b=await pos();const d=mv(a,b);
   const want=Object.values(m.law).filter(v=>(v.state==="hit"&&v.confidence!=="low")||v.state==="gap").length,got=await p.evaluate(()=>PT.length);
   if(d<16)fail(`${pr.short} satellites moved ${d.toFixed(1)}px in 3s (< 16)`);if(got!==want)fail(`${pr.short} flow particles ${got} != ${want}`);
   await p.evaluate(()=>document.getElementById("svg").dispatchEvent(new PointerEvent("pointerenter")));await p.waitForTimeout(300);a=await pos();await p.waitForTimeout(1500);b=await pos();
   if(mv(a,b)>0.5)fail(`${pr.short} still moving while the pointer is over the graph`);
   n++;await p.close()}}
 else if(arg==="--ring"){const M=mock();for(const pr of P){const p=await open(pr.id),m=M.projects[pr.id];await p.evaluate(()=>{orbitPaused=true});
   for(const k of Object.keys(m.law).filter(k=>m.law[k].state==="hit"||m.law[k].state==="gap")){
    await p.evaluate(k=>{kvSel=k;render()},k);await p.waitForTimeout(80);
    const hit=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),ring=document.querySelector("[data-kv-ring]")||document.querySelector("[data-kv-selected] circle[stroke=\"#a9e3dc\"]");if(!ring)return"no ring";const r=R(ring),cx=r.left+r.width/2,cy=r.top+r.height/2,rad=r.width/2;
      for(const t of document.querySelectorAll("svg text")){const b=R(t),nx=Math.max(b.left,Math.min(cx,b.right)),ny=Math.max(b.top,Math.min(cy,b.bottom));if(Math.hypot(nx-cx,ny-cy)<rad+1)return"ring touches '"+t.textContent+"'"}return""});
    if(hit)fail(`${pr.short} ${k}: ${hit}`)}
   n++;await p.close()}}
 else if(arg==="--select"){const M=mock();for(const pr of P){const p=await open(pr.id),m=M.projects[pr.id];
   // click a satellite by its real on-screen centre (the graph redraws continuously, so pause motion first)
   await p.evaluate(()=>{orbitPaused=true});await p.waitForTimeout(150);
   const clickKey=async k=>{const c=await p.evaluate(k=>{const g=document.querySelector(`[data-kv-key="${k}"]`),b=(g.querySelector("image,circle[stroke]")||g).getBoundingClientRect();return{x:b.left+b.width/2,y:b.top+b.height/2}},k);await p.mouse.click(c.x,c.y);await p.waitForTimeout(250)};
   const state=()=>p.evaluate(()=>[...document.querySelectorAll("[data-kv-key]")].map(g=>({k:g.getAttribute("data-kv-key"),sel:g.hasAttribute("data-kv-selected"),o:+g.getAttribute("opacity")})));
   const hit=Object.keys(m.law).find(k=>m.law[k].state==="hit"),gap=Object.keys(m.law).find(k=>m.law[k].state==="gap"),na=Object.keys(m.law).find(k=>m.law[k].state==="na");
   for(const k of [hit,gap]){await clickKey(k);const S=await state(),me=S.find(x=>x.k===k),others=S.filter(x=>x.k!==k);
    if(!me.sel)fail(`${pr.short} ${k} not selected`);if(others.some(x=>x.sel))fail(`${pr.short} more than one selected`);if(!others.every(x=>x.o<me.o))fail(`${pr.short} ${k}: others not faded`)}
   const b=await p.evaluate(()=>{const s=document.getElementById("svg").getBoundingClientRect();return{x:s.left+8,y:s.top+s.height/2}});await p.mouse.click(b.x,b.y);await p.waitForTimeout(250);
   let S=await state();if(S.some(x=>x.sel||x.o<1))fail(`${pr.short} blank click did not clear selection`);
   await clickKey(na);S=await state();if(S.some(x=>x.sel||x.o<1))fail(`${pr.short} clicking na (${na}) must not select or fade`);
   if(m.uncovered.length){await p.waitForTimeout(800);await clickKey(m.uncovered[0]);S=await state();if(S.some(x=>x.sel||x.o<1))fail(`${pr.short} clicking uncovered must not select or fade`)}
   n++;await p.close()}}
 else if(arg==="--supplement"){const M=mock();for(const pr of P){const p=await open(pr.id),m=M.projects[pr.id],gap=Object.keys(m.law).find(k=>m.law[k].state==="gap");
   const before=await p.evaluate(()=>Object.fromEntries([...document.querySelectorAll("[data-kv-key]")].map(g=>[g.getAttribute("data-kv-key"),g.getAttribute("data-kv-state")])));
   // simulate Eva's confirmation exactly as the parent frame delivers it
   await p.evaluate(k=>window.dispatchEvent(new MessageEvent("message",{data:{type:"dd-confirmed",subject:1,code:k,text:"測試補充"},origin:location.origin,source:window.parent})),gap);await p.waitForTimeout(300);
   const r=await p.evaluate(k=>{const g=document.querySelector(`[data-kv-key="${k}"]`);return{state:g.getAttribute("data-kv-state"),text:g.textContent,glow:!!g.querySelector('circle[fill="url(#kv-glow)"]'),fog:!!g.querySelector('circle[fill="url(#kv-fog)"]'),
     all:Object.fromEntries([...document.querySelectorAll("[data-kv-key]")].map(x=>[x.getAttribute("data-kv-key"),x.getAttribute("data-kv-state")]))}},gap);
   if(r.state!=="supplemented")fail(`${pr.short} ${gap} state ${r.state}`);if(!r.text.includes("已補充・待重判"))fail(`${pr.short} ${gap} missing 已補充・待重判`);
   if(/風險|提醒/.test(r.text))fail(`${pr.short} ${gap} supplemented must not show risk/note counts`);if(r.glow)fail(`${pr.short} ${gap} supplemented must not get the 對上了 glow`);if(r.fog)fail(`${pr.short} ${gap} fog not cleared`);
   for(const [k,v] of Object.entries(before))if(k!==gap&&r.all[k]!==v)fail(`${pr.short} ${k} changed ${v}->${r.all[k]}`);
   n++;await p.close()}}
 else if(arg==="--hygiene"){for(const pr of P){const p=await open(pr.id);let s=await snap(p);if(s.dash)fail(pr.short+" dashes in topic view");await toDomain(p);s=await snap(p);if(s.dash)fail(pr.short+" dashes in domain view");
   if(p._errs.length)fail(pr.short+" page errors: "+p._errs.join(";"));if(p._ext.length)fail(pr.short+" external requests: "+p._ext.join(","));n++;await p.close()}}
 else{console.error("flags: --record-baseline | --default-unchanged | --domain | --toggle-back | --no-overlap | --hygiene");process.exitCode=2}
 await b.close();srv.close();if(!process.exitCode)console.log("OK",arg,n?n+" projects":"")})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
