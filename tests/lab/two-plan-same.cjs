// Two-plan equivalence: the original and the new tangle-match.html must draw the SAME two-plan view.
// Freezes time-based motion (performance.now) so frames are deterministic, then compares the full SVG markup
// and the flow particles, for many pairs, idle and focused. Usage: node two-plan-same.cjs <origDir> <newDir>
const http=require('http'),fs=require('fs'),path=require('path');const{chromium}=require('playwright');
const MIME={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8'};
const serve=root=>http.createServer((q,r)=>{const f=path.join(root,decodeURIComponent(q.url.split('?')[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{'Content-Type':MIME[path.extname(f)]||'application/octet-stream'});r.end(d)}})});
const [A,B]=process.argv.slice(2);
const src=fs.readFileSync(path.join(B,'tangle/kv-match-mock.js'),'utf8'),M=JSON.parse(src.slice(src.indexOf('{'),src.lastIndexOf('}')+1)),IDS=Object.keys(M.projects);
const PAIRS=[];for(let i=0;i<IDS.length;i++)for(let j=i+1;j<IDS.length;j++)PAIRS.push([IDS[i],IDS[j]]);
(async()=>{const sa=serve(A),sb=serve(B);await new Promise(r=>sa.listen(0,'127.0.0.1',r));await new Promise(r=>sb.listen(0,'127.0.0.1',r));
 const b=await chromium.launch();let bad=0,n=0;
 const snap=async(port,a,c,mode)=>{const p=await b.newPage({viewport:{width:1100,height:740}});
  // deterministic: Math.random fixed, performance.now frozen after load
  await p.addInitScript(()=>{let s=1;Math.random=()=>{s=(s*16807)%2147483647;return s/2147483647};let t=0;performance.now=()=>(t+=16);window.__freeze=()=>{const T=12345;performance.now=()=>T}});
  await p.goto(`http://127.0.0.1:${port}/tangle/tangle-match.html?p=${a}&q=${c}`);await p.waitForTimeout(2600);
  await p.evaluate(()=>{window.__freeze();IDLE=false;ENT=1;VZ=1.2;VX=Wd/2*(1-VZ);VY=Hd/2*(1-VZ);P.forEach(q=>{pos[q.id].pin=false});tick(1)});
  if(mode==='focus')await p.evaluate(()=>{focus=P[0].id;syncMode();draw()});
  await p.evaluate(()=>{render();buildParticles()});
  const out=await p.evaluate(()=>({svg:document.getElementById('svg').innerHTML.replace(/ data-mf-pair="[^"]*"/g,''),pt:PT.length,tr:TRACKS.length}));
  await p.close();return out};
 for(const [a,c] of PAIRS)for(const mode of ['idle','focus']){const x=await snap(sa.address().port,a,c,mode),y=await snap(sb.address().port,a,c,mode);n++;
  if(x.svg!==y.svg||x.pt!==y.pt||x.tr!==y.tr){bad++;if(bad<=3){let i=0;while(i<x.svg.length&&x.svg[i]===y.svg[i])i++;console.log(`DIFF ${a}×${c} ${mode}: tracks ${x.tr}/${y.tr} particles ${x.pt}/${y.pt} | at ${i}: …${x.svg.slice(i-60,i+80)}… vs …${y.svg.slice(i-60,i+80)}…`)}}}
 await b.close();sa.close();sb.close();
 console.log(bad?`DIFFERENT ${bad}/${n}`:`SAME ${n} two-plan views (45 pairs × idle/focus)`);process.exit(bad?1:0)})().catch(e=>{console.error(e.message);process.exit(1)});
