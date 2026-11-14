// Step 2a end-to-end on the live lab (real mouse). LAB_URL, LAB_PASS. Needs Playwright via NODE_PATH.
// Every step prints "ok <what>"; any failure exits 1. Last line: "ALL OK <n>".
const fs=require("fs"),path=require("path");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS,PID="48060125";
const mockSrc=fs.readFileSync(path.resolve(__dirname,"..","..","public","tangle","kv-law-mock.js"),"utf8");
const M=JSON.parse(mockSrc.slice(mockSrc.indexOf("{"),mockSrc.lastIndexOf("}")+1)).projects[PID];
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[],ext=new Set();
 p.on("pageerror",e=>errs.push(e.message));p.on("request",r=>{const h=new URL(r.url()).host;if(!U.includes(h))ext.add(h)});
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  await p.getByRole("button",{name:/法規檢核/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().find(f=>f.url().includes("/public/workspace/embed.html"));ok(!!W,"法規 workspace opened");
  await W.selectOption('select[aria-label="分析專案"]',PID);await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=()=>p.frames().find(f=>f.url().includes("tangle-law"));ok(!!G(),"law graph loaded");
  await G().evaluate(()=>{orbitPaused=true});
  const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
  const at=async k=>{await p.mouse.move(ib.x+20,ib.y+40);await p.waitForTimeout(150);const c=await G().evaluate(k=>{const g=document.querySelector(`[data-kv-key="${k}"]`),r=(g.querySelector("image,circle[stroke]")||g).getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}},k);return{x:ib.x+c.x,y:ib.y+c.y}};
  const click=async k=>{const c=await at(k);await p.mouse.click(c.x,c.y);await p.waitForTimeout(2500)};
  const chat=()=>p.locator("#root").innerText();
  const kvState=k=>G().evaluate(k=>document.querySelector(`[data-kv-key="${k}"]`).getAttribute("data-kv-state"),k);

  // 對上了
  const hit="農村再生";await click(hit);
  ok(await G().evaluate(k=>document.querySelector(`[data-kv-key="${k}"]`).hasAttribute("data-kv-selected"),hit),"對上了 satellite is selected");
  ok((await G().evaluate(()=>document.querySelectorAll("[data-kv-dim]").length))>=9,"other satellites fade");
  let t=await chat();ok(t.includes(M.law[hit].evidence[0]),"Eva quotes the plan text for 對上了");
  ok(t.includes("9 條提醒")&&t.includes("示範資料"),"Eva states the demo count and the demo disclaimer");

  // 缺資料 -> supplement -> cancel (no change) -> supplement -> confirm (supplemented)
  const gap="開發審議";await click(gap);t=await chat();ok(t.includes(M.law[gap].question),"Eva asks the gap question from the data");
  const box=p.locator("#chat-input, textarea").first();
  await box.click();await p.keyboard.type("先取消這一則");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"取消"}).last().click();await p.waitForTimeout(2500);
  ok(await kvState(gap)==="gap","cancel leaves the satellite unchanged");
  await click(gap);await box.click();await p.keyboard.type("基地約 0.3 公頃，社區活動中心旁");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  ok((await chat()).includes("確認補充到「開發審議」"),"Eva asks to confirm the supplement first");
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(3500);
  ok(await kvState(gap)==="supplemented","confirmed supplement turns the satellite into supplemented");
  const lbl=await G().evaluate(k=>document.querySelector(`[data-kv-key="${k}"]`).textContent,gap);
  ok(lbl.includes("已補充・待重判")&&!/風險|提醒/.test(lbl),"label says 已補充・待重判 with no risk/note counts");
  ok((await chat()).includes("示範版不會重新判斷"),"Eva says the demo will not re-judge");

  // 不適用 / 未收錄: flash only, fixed wording
  const na=Object.keys(M.law).find(k=>M.law[k].state==="na");await click(na);
  ok((await G().evaluate(()=>document.querySelectorAll("[data-kv-dim],[data-kv-selected]").length))===0,"clicking 不適用 neither selects nor fades");
  ok((await chat()).includes(`沒有和「${na}」相關的內容`),"Eva's 不適用 wording");
  await p.waitForTimeout(800);await click(M.uncovered[0]);
  ok((await chat()).includes("沒檢查不代表合規"),"Eva's 未收錄 wording");

  // close restores
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);
  ok(!(await p.evaluate(()=>document.body.classList.contains("tangle-ws-on"))),"收合 closes the workspace");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  const allowed=["fonts.googleapis.com","fonts.gstatic.com","cdn.jsdelivr.net","static.cloudflareinsights.com"];
  const bad=[...ext].filter(h=>!allowed.includes(h));ok(bad.length===0,"no requests to other hosts"+(bad.length?": "+bad.join(","):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
