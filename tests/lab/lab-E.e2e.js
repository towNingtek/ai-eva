// Step E on the live lab (real mouse): law status text, Eva asks one question, answer → rule re-judge → graph and
// status follow; 還不知道 keeps it 缺資料. LAB_URL, LAB_PASS; Playwright via NODE_PATH. Last line "ALL OK <n>".
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  // 大庄: 開發審議 and 環評 are 缺資料
  await p.getByRole("button",{name:/⚖ 法規檢核/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();await W.selectOption('select[aria-label="分析專案"]',"48060125");
  await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=()=>p.frames().filter(f=>f.url().includes("tangle-law")).pop();const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
  const status=()=>G().evaluate(()=>{const g=document.querySelector("[data-law-status]");return g?{st:g.getAttribute("data-law-status"),t:g.textContent}:null});
  const state=k=>G().evaluate(k=>document.querySelector(`[data-kv-key="${k}"]`)?.getAttribute("data-kv-state"),k);
  let s=await status();ok(s&&s.st==="CLARIFY_FIRST"&&s.t.includes("先補資料"),"law status shows 先補資料");
  ok(await state("開發審議")==="gap","開發審議 starts as 缺資料");
  // click the 開發審議 satellite with the mouse → Eva replies and asks the area question
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-20);await p.waitForTimeout(400);
  const c=await G().evaluate(()=>{const g=document.querySelector('[data-kv-key="開發審議"] circle[fill="transparent"]');const r=g.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+c.x,ib.y+c.y);await p.waitForTimeout(4000);
  let t=await p.locator("#root").innerText();
  ok(t.includes("推論（AI，未經 Owner 確認）")&&t.includes("事實"),"Eva labels 事實 and 推論");
  ok(t.includes("基地面積多大")&&t.includes("還不知道")&&t.includes("跳過"),"Eva asks ONE question (area) with 還不知道 / 跳過");
  // answer 0.8 公頃 → rule (§11 ≥1 公頃) → 不觸及
  const box=p.locator("#chat-input, textarea").first();
  await box.click();await p.keyboard.type("大約 0.8 公頃");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(5000);
  t=await p.locator("#root").innerText();
  ok(/不觸及/.test(t)&&t.includes("使用者陳述・未查證"),"0.8 公頃 → Eva: 不觸及 by the threshold rule, marked 未查證");
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-20);await p.waitForTimeout(1200);
  ok(await state("開發審議")==="na","the graph moves 開發審議 to 未涉及");
  // next question is 環評; answer 還不知道 → stays 缺資料, status stays 先補資料
  ok(/工程的規模|山坡地/.test(t),"Eva moves on to the next question (環評)");
  await p.getByRole("button",{name:"還不知道"}).last().click();await p.waitForTimeout(3500);
  t=await p.locator("#root").innerText();ok(t.includes("不算補齊"),"還不知道 is recorded but not counted");
  ok(await state("環境影響評估")==="gap","環評 stays 缺資料");
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-20);await p.waitForTimeout(300);
  await G().evaluate(()=>{if(typeof kvLeave==="function")kvLeave()});await p.waitForTimeout(1500);
  s=await status();ok(s&&s.st==="CLARIFY_FIRST","back on the overview: law status still 先補資料 (環評 not answered)");
  // an answer the rule cannot read keeps the old mark: 已補充・待重判 (old effect kept)
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-20);await p.waitForTimeout(300);
  const c2=await G().evaluate(()=>{const g=document.querySelector('[data-kv-key="環境影響評估"] circle[fill="transparent"]');const r=g.getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+c2.x,ib.y+c2.y);await p.waitForTimeout(3500);
  await box.click();await p.keyboard.type("規模還在跟鄉公所討論");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(4500);
  t=await p.locator("#root").innerText();ok(t.slice(t.lastIndexOf("已記下")).includes("看不出數字")&&t.slice(t.lastIndexOf("已記下")).includes("已補充・待重判"),"an unreadable answer is kept as 已補充・待重判 (old mark)");
  await G().evaluate(()=>{if(typeof kvLeave==="function")kvLeave()});await p.waitForTimeout(1500);
  ok(await state("環境影響評估")==="supplemented","the graph shows 已補充 for that satellite");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
