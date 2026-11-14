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
 const toDomain=async p=>{await p.locator('[data-kv-view="domain"]').click();await p.waitForTimeout(700)};
 const toTopic=async p=>{await p.locator('[data-kv-view="topic"]').click();await p.waitForTimeout(700)};
 if(arg==="--record-baseline"){const out={};for(const pr of P){const p=await open(pr.id);const s=await snap(p);out[pr.id]={rules:s.rules,planet:s.planet,vz:s.vz};await p.close()}fs.writeFileSync(BASE,JSON.stringify(out,null,1));console.log("baseline recorded for",Object.keys(out).length,"projects")}
 else if(arg==="--default-unchanged"){const base=JSON.parse(fs.readFileSync(BASE,"utf8"));for(const pr of P){const p=await open(pr.id),s=await snap(p);
   if(JSON.stringify({rules:s.rules,planet:s.planet,vz:s.vz})!==JSON.stringify(base[pr.id]))fail(pr.short+" default view differs from baseline");
   if(s.rules.length!==pr.issues.length)fail(pr.short+" topic satellites "+s.rules.length+" != "+pr.issues.length);if(s.kv.length)fail(pr.short+" kv satellites visible in default view");if(s.demo)fail(pr.short+" demo note visible in default view");n++;await p.close()}}
 else if(arg==="--domain"){const M=mock();for(const pr of P){const p=await open(pr.id);await toDomain(p);const s=await snap(p),m=M.projects[pr.id];
   const core=s.kv.filter(k=>k.state!=="uncovered"),unc=s.kv.filter(k=>k.state==="uncovered");
   if(core.length!==10||core.map(k=>k.key).sort().join()!==[...DOMAINS].sort().join())fail(pr.short+" domain keys wrong: "+core.map(k=>k.key).join());
   for(const k of core)if(m.law[k.key].state!==k.state)fail(`${pr.short} ${k.key} state ${k.state} != mock ${m.law[k.key].state}`);
   if(unc.length!==m.uncovered.length||unc.map(k=>k.key).sort().join()!==[...m.uncovered].sort().join())fail(pr.short+" uncovered mismatch");
   if(s.rules.length)fail(pr.short+" topic satellites still visible in domain view");if(!s.demo)fail(pr.short+" demo note missing");if(s.planet!==1)fail(pr.short+" planet count "+s.planet);n++;await p.close()}}
 else if(arg==="--toggle-back"){for(const pr of P){const p=await open(pr.id),a=await snap(p);await toDomain(p);await toTopic(p);const c=await snap(p);
   if(JSON.stringify(a.rules)!==JSON.stringify(c.rules)||c.kv.length||c.demo||a.vz!==c.vz)fail(pr.short+" did not return to the original topic view");n++;await p.close()}}
 else if(arg==="--no-overlap"){for(const pr of P){for(const vp of [{width:812,height:588},{width:1100,height:740}]){const p=await open(pr.id);await p.setViewportSize(vp);await p.waitForTimeout(400);await toDomain(p);
   const hits=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),X=(a,b)=>a.left<b.right&&b.left<a.right&&a.top<b.bottom&&b.top<a.bottom;const fixed=["#kvDemo","#kvView","#zc"].map(s=>[s,R(document.querySelector(s))]);
     const U=g=>{const rs=[...g.querySelectorAll("text")].map(R);return{left:Math.min(...rs.map(r=>r.left)),top:Math.min(...rs.map(r=>r.top)),right:Math.max(...rs.map(r=>r.right)),bottom:Math.max(...rs.map(r=>r.bottom))}};const labels=[...document.querySelectorAll("[data-kv-key],[data-project-planet]")].map(g=>[g.getAttribute("data-kv-key")||"專案名稱",U(g)]);const out=[];
     for(const [t,r] of labels){for(const [s,f] of fixed)if(X(r,f))out.push(t+" × "+s);if(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)out.push(t+" clipped")}
     for(let i=0;i<labels.length;i++)for(let j=i+1;j<labels.length;j++)if(X(labels[i][1],labels[j][1]))out.push(labels[i][0]+" × "+labels[j][0]);const bodies=[...document.querySelectorAll("[data-kv-key]")].map(g=>{const b=R(g.querySelector("image,circle[stroke]")||g);return[g.getAttribute("data-kv-key"),b.left+b.width/2,b.top+b.height/2,Math.max(b.width,b.height)/2]});document.querySelectorAll('path[stroke^="url(#kv-route"]').forEach(pth=>{const L=pth.getTotalLength(),m=pth.getScreenCTM();const end=pth.getPointAtLength(L),ex=end.x*m.a+m.e,ey=end.y*m.d+m.f;for(let k=1;k<40;k++){const q=pth.getPointAtLength(L*k/40),x=q.x*m.a+m.e,y=q.y*m.d+m.f;for(const [name,bx,by,br] of bodies){if(Math.hypot(ex-bx,ey-by)<br+30)continue;if(Math.hypot(x-bx,y-by)<br+4){out.push("route crosses "+name);return}}}});return [...new Set(out)]});
   if(hits.length)fail(`${pr.short} @${vp.width}x${vp.height}: ${hits.slice(0,4).join(" | ")}`);await p.close()}n++}}
 else if(arg==="--hygiene"){for(const pr of P){const p=await open(pr.id);let s=await snap(p);if(s.dash)fail(pr.short+" dashes in topic view");await toDomain(p);s=await snap(p);if(s.dash)fail(pr.short+" dashes in domain view");
   if(p._errs.length)fail(pr.short+" page errors: "+p._errs.join(";"));if(p._ext.length)fail(pr.short+" external requests: "+p._ext.join(","));n++;await p.close()}}
 else{console.error("flags: --record-baseline | --default-unchanged | --domain | --toggle-back | --no-overlap | --hygiene");process.exitCode=2}
 await b.close();srv.close();if(!process.exitCode)console.log("OK",arg,n?n+" projects":"")})().catch(e=>{console.error("ERROR",e.message);process.exit(1)});
