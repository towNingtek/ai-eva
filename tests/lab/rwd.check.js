// RWD: law (10 plans) and match (45 pairs) at 390 / 600 / 1100 px — no two different labels overlap, nothing leaves
// the screen, no page errors. Static server over public/, no network. Usage: node tests/lab/rwd.check.js [--law|--match]
// Prints "OK rwd <n> views" or FAIL lines; exit 1 on any failure.
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const http=require("http"),fs=require("fs"),path=require("path");
const ROOT=process.env.ROOT||path.join(__dirname,"..","..","public");const MIME={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",".css":"text/css"};
const s=http.createServer((q,r)=>{const f=path.join(ROOT,decodeURIComponent(q.url.split("?")[0]));fs.readFile(f,(e,d)=>{if(e){r.writeHead(404);r.end()}else{r.writeHead(200,{"Content-Type":MIME[path.extname(f)]||"application/octet-stream"});r.end(d)}})});
const src=fs.readFileSync(path.join(ROOT,"tangle","kv-match-mock.js"),"utf8"),M=JSON.parse(src.slice(src.indexOf("{"),src.lastIndexOf("}")+1)),IDS=Object.keys(M.projects);
const PAIRS=[];for(let i=0;i<IDS.length;i++)for(let j=i+1;j<IDS.length;j++)PAIRS.push([IDS[i],IDS[j]]);
const only=process.argv[2];let fails=0,n=0;const fail=m=>{fails++;console.log("FAIL",m)};
(async()=>{await new Promise(r=>s.listen(0,"127.0.0.1",r));const b=await chromium.launch();
 for(const w of [390,600,1100]){const h=w<700?720:740;
  for(const kind of ["law","match"]){if(only&&only!=="--"+kind)continue;
   const urls=kind==="law"?IDS.map(id=>`/tangle/tangle-law.html?p=${id}`):PAIRS.map(([a,c])=>`/tangle/tangle-match.html?p=${a}&q=${c}`);
   for(const u of urls){const p=await b.newPage({viewport:{width:w,height:h}});const pe=[];p.on("pageerror",e=>pe.push(e.message));
    await p.goto(`http://127.0.0.1:${s.address().port}${u}`);await p.mouse.move(1,1);await p.waitForTimeout(2400);
    const r=await p.evaluate(()=>{const R=e=>e.getBoundingClientRect(),X=(a,b)=>a.left<b.right-1&&b.left<a.right-1&&a.top<b.bottom-1&&b.top<a.bottom-1;
     const T=[...document.querySelectorAll("#svg text")].filter(t=>t.textContent.trim()&&+(t.getAttribute("opacity")??1)>.05&&getComputedStyle(t).display!=="none").map(t=>[t.textContent,R(t),t.parentNode]);const o=[],c=[];
     for(let i=0;i<T.length;i++)for(let j=i+1;j<T.length;j++)if(T[i][2]!==T[j][2]&&X(T[i][1],T[j][1]))o.push(T[i][0]+" × "+T[j][0]);
     for(const [t,r] of T)if(r.left<-1||r.top<-1||r.right>innerWidth+1||r.bottom>innerHeight+1)c.push(t);return{o,c}});
    const tag=`${kind} @${w} ${u.split("?")[1]}`;if(r.o.length)fail(`${tag}: overlap ${r.o[0]}`);if(r.c.length)fail(`${tag}: off screen ${r.c[0]}`);if(pe.length)fail(`${tag}: page error ${pe[0]}`);
    n++;await p.close()}}}
 await b.close();s.close();if(fails)process.exit(1);console.log(`OK rwd ${n} views (law + match × 390/600/1100)`)})().catch(e=>{console.error(e.message);process.exit(1)});
