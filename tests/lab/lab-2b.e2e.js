// Step 2b end-to-end on the live lab (real mouse): walk into a satellite and back. LAB_URL, LAB_PASS; Playwright via NODE_PATH.
// Every step prints "ok <what>"; any failure exits 1. Last line: "ALL OK <n>".
const fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS,PID="48060125";
const src=fs.readFileSync(path.resolve(__dirname,"..","..","public","tangle","kv-law-mock.js"),"utf8");
const M=JSON.parse(src.slice(src.indexOf("{"),src.lastIndexOf("}")+1)).projects[PID];
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[],ext=new Set();
 p.on("pageerror",e=>errs.push(e.message));p.on("request",r=>{const h=new URL(r.url()).host;if(!U.includes(h))ext.add(h)});
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  await p.getByRole("button",{name:/⚖ 法規檢核/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().find(f=>f.url().includes("/public/workspace/embed.html"));await W.selectOption('select[aria-label="分析專案"]',PID);await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=()=>p.frames().find(f=>f.url().includes("tangle-law"));ok(!!G(),"law graph loaded");
  const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox(),gf=p.frameLocator("#tangle-ws iframe").frameLocator("iframe.original-tangle");
  const click=async k=>{await p.mouse.move(ib.x+20,ib.y+40);await p.waitForTimeout(150);const c=await G().evaluate(k=>{const g=document.querySelector(`[data-kv-key="${k}"]`),r=(g.querySelector("image,circle[stroke]")||g).getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}},k);await p.mouse.click(ib.x+c.x,ib.y+c.y);await p.waitForTimeout(2500)};
  const view=()=>G().evaluate(()=>({focus:document.querySelector("[data-focus]")?.getAttribute("data-focus")||null,debris:document.querySelectorAll("[data-clause]").length,risk:document.querySelectorAll('[data-clause-kind="risk"]').length}));
  const chat=()=>p.locator("#root").innerText();

  const hit="非都市土地使用管制",v=M.law[hit];await click(hit);let V=await view();
  ok(V.focus===hit,"clicking 對上了 walks into the satellite");
  ok(V.debris===v.clauses.length&&V.risk===v.count.risk,`clause debris shown: ${V.debris} (${V.risk} risk) = data`);
  let t=await chat();ok(v.clauses.every(c=>t.includes(`${c.law} ${c.no}`)),"Eva lists every clause by law and article");
  ok(t.includes("示範假設"),"Eva says which clauses match is a demo assumption");
  await gf.locator("#kvBack").click();await p.waitForTimeout(1500);V=await view();ok(!V.focus,"← 返回專案星系 walks back out");
  await click("農村再生");V=await view();ok(V.focus==="農村再生","walk into another domain");
  await p.mouse.move(ib.x+ib.width/2,ib.y+40);await p.keyboard.press("Escape");await p.waitForTimeout(1500);V=await view();ok(!V.focus,"Esc walks back out");

  // walk into a gap, supplement while inside: still works and shows 已補充・待重判
  const gap="開發審議";await click(gap);V=await view();ok(V.focus===gap&&V.debris===0,"缺資料 walks in without debris");
  ok((await chat()).includes(M.law[gap].question),"Eva asks the gap question");
  const box=p.locator("#chat-input, textarea").first();await box.click();await p.keyboard.type("基地約 0.3 公頃");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(3500);
  // step E: answering inside the focus view re-judges by rule (0.3 公頃 < 1 公頃 → 不觸及); back on the overview it is 未涉及
  await G().evaluate(()=>{if(typeof kvLeave==="function")kvLeave()});await p.waitForTimeout(1500);
  const st=await G().evaluate(k=>document.querySelector(`[data-kv-key="${k}"]`)?.getAttribute("data-kv-state"),gap);
  ok(st==="na"&&/不觸及/.test(await chat()),"supplement inside the focus view is re-judged by rule (不觸及 → 未涉及)");

  const na=Object.keys(M.law).find(k=>M.law[k].state==="na");await click(na);V=await view();ok(!V.focus,"clicking 不適用 leaves the focus view and does not walk in");
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);
  ok(!(await p.evaluate(()=>document.body.classList.contains("tangle-ws-on"))),"收合 closes the workspace");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  const allowed=["fonts.googleapis.com","fonts.gstatic.com","cdn.jsdelivr.net","static.cloudflareinsights.com"],bad=[...ext].filter(h=>!allowed.includes(h));
  ok(bad.length===0,"no requests to other hosts"+(bad.length?": "+bad.join(","):""));
  await p.screenshot({path:"/tmp/s2b-last.png"});console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
