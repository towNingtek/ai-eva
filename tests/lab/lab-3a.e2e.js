// Step 3a end-to-end on the live lab (real mouse): match view shows B1–B8 need/offer and Eva answers a B satellite.
// LAB_URL, LAB_PASS; Playwright via NODE_PATH. Every step prints "ok <what>"; any failure exits 1; last line "ALL OK <n>".
const fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS,A="85457156",B="15080750";   // 林中 × 水尾
const src=fs.readFileSync(path.resolve(__dirname,"..","..","public","tangle","kv-match-mock.js"),"utf8");
const M=JSON.parse(src.slice(src.indexOf("{"),src.lastIndexOf("}")+1));
const role=(pid,k)=>M.projects[pid].match[k].role;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[],ext=new Set();
 p.on("pageerror",e=>errs.push(e.message));p.on("request",r=>{const h=new URL(r.url()).host;if(!U.includes(h))ext.add(h)});
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().find(f=>f.url().includes("/public/workspace/embed.html"));ok(!!W,"媒合 workspace opened");
  await W.selectOption('select[aria-label="分析專案"]',A);await p.waitForTimeout(300);
  const opt=await W.locator('select[aria-label="合作對象"] option[value="'+B+'"]').textContent();ok(/可對接 \d+/.test(opt),"partner list shows 可對接 count: "+opt.trim());
  await W.selectOption('select[aria-label="合作對象"]',B);await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=()=>p.frames().find(f=>f.url().includes("tangle-match"));ok(!!G(),"match graph loaded");
  const S=await G().evaluate(()=>[...document.querySelectorAll("[data-kv-key]")].map(g=>({k:g.getAttribute("data-kv-key"),role:g.getAttribute("data-kv-role"),owner:g.getAttribute("data-kv-owner"),shadow:g.querySelector("[data-need-shadow]")?.getAttribute("data-need-shadow")||null,text:g.textContent})));
  const exp=[A,B].flatMap(pid=>Object.keys(M.keys).filter(k=>role(pid,k)!=="none").map(k=>pid+":"+k)).sort();
  ok(S.map(s=>s.owner+":"+s.k).sort().join()===exp.join(),`satellites are exactly the B1–B8 need/offer keys (${S.length})`);
  ok(S.every(s=>s.role===role(s.owner,s.k)),"every satellite carries the right 需要／能提供 role");
  ok(S.filter(s=>s.role==="need").every(s=>s.shadow==="met"||s.shadow==="unmet")&&S.filter(s=>s.role==="offer").every(s=>!s.shadow),"needs are crescents, offers are fully lit");
  const unmet=S.find(s=>s.shadow==="unmet");ok(unmet&&unmet.text.includes("沒有對象"),"an unmet need says 沒有對象: "+(unmet&&unmet.k));
  const routes=(await G().evaluate(()=>TRACKS.map(t=>t.tag))).sort(),expR=Object.keys(M.keys).filter(k=>(role(A,k)==="need"&&role(B,k)==="offer")||(role(B,k)==="need"&&role(A,k)==="offer")).sort();
  ok(routes.join()===expR.join(),`routes = need × offer: ${routes.join(" ")}`);
  // click a met need with a real mouse; Eva answers with the quote and the role
  const tgt=S.find(s=>s.shadow==="met");const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
  await p.mouse.move(ib.x+20,ib.y+40);await p.waitForTimeout(200);
  const c=await G().evaluate(([k,o])=>{const r=document.querySelector(`[data-kv-key="${k}"][data-kv-owner="${o}"] image`).getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}},[tgt.k,tgt.owner]);
  await p.mouse.click(ib.x+c.x,ib.y+c.y);await p.waitForTimeout(3000);
  const t=await p.locator("#root").innerText(),v=M.projects[tgt.owner].match[tgt.k];
  ok(t.includes(v.evidence[0]),"Eva quotes the plan text for the clicked B satellite");
  ok(t.includes("需要")&&t.includes("互補候選")&&t.includes("示範資料"),"Eva states 需要, that it is a 互補候選 (standard v1.1), and the demo note");
  // 3a+: flow is visible (3 particles per route) and a both-offer pair shows a faint, still peer line that Eva explains
  ok((await G().evaluate(()=>{const c={};PT.forEach(q=>c[q.ti]=(c[q.ti]||0)+1);return TRACKS.every((t,i)=>t.peer||c[i]===3)})),"every need×offer route carries 3 flow particles");
  await p.reload();await p.waitForTimeout(6000);
  await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
  const W2=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();
  await W2.selectOption('select[aria-label="分析專案"]',"48060125");await p.waitForTimeout(300);await W2.selectOption('select[aria-label="合作對象"]',"26791874");
  await W2.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G2=()=>p.frames().filter(f=>f.url().includes("tangle-match")).pop();
  const peers=await G2().evaluate(()=>[...document.querySelectorAll("[data-kv-peer]")].map(x=>x.getAttribute("data-kv-peer")));
  ok(peers.join()==="B6","大庄 × 大德: one peer line, 社群與關係 (both offer)");
  ok(await G2().evaluate(()=>!PT.some(q=>TRACKS[q.ti]&&TRACKS[q.ti].peer)),"the peer line has no flow");
  const ib2=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();await p.mouse.move(ib2.x+20,ib2.y+40);await p.waitForTimeout(200);
  const mid=await G2().evaluate(()=>{const pth=document.querySelector("[data-kv-peer]"),pt=pth.getPointAtLength(pth.getTotalLength()*.5),m=pth.getScreenCTM();return{x:pt.x*m.a+m.e,y:pt.y*m.d+m.f}});
  await p.mouse.click(ib2.x+mid.x,ib2.y+mid.y);await p.waitForTimeout(3000);
  const t2=await p.locator("#root").innerText();
  ok(t2.includes("兩邊都能提供")&&t2.includes("交流經驗"),"clicking the peer line: Eva says both offer it and it is for sharing experience");
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);
  ok(!(await p.evaluate(()=>document.body.classList.contains("tangle-ws-on"))),"收合 closes the workspace");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  const allowed=["fonts.googleapis.com","fonts.gstatic.com","cdn.jsdelivr.net","static.cloudflareinsights.com"],bad=[...ext].filter(h=>!allowed.includes(h));
  ok(bad.length===0,"no requests to other hosts"+(bad.length?": "+bad.join(","):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
