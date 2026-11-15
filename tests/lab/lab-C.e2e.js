// Step C on the live lab (real mouse): status pill, Eva asks one question at a time, answering the two minimum
// fields moves 先補資料 → 可探索 (by rule), both-need line, BOTH satellite. LAB_URL, LAB_PASS; Playwright via NODE_PATH.
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  // 林中 × 水尾: 3 complementary candidates (B1 B3 B4), nothing filled → 先補資料
  await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();await W.selectOption('select[aria-label="分析專案"]',"85457156");await p.waitForTimeout(300);await W.selectOption('select[aria-label="合作對象"]',"15080750");
  await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=()=>p.frames().filter(f=>f.url().includes("tangle-match")).pop();const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
  const pill=()=>G().evaluate(()=>{const g=document.querySelector("[data-mf-status]");return g?{st:g.getAttribute("data-mf-status"),t:g.textContent}:null});
  let s=await pill();ok(s&&s.st==="CLARIFY_FIRST"&&s.t.includes("先補資料"),"status pill shows 先補資料 (candidates, nothing filled)");
  // click the pill → Eva explains + asks the first question (NEED minimum field: 用途)
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-20);await p.waitForTimeout(300);
  const pc=await G().evaluate(()=>{const r=document.querySelector("[data-mf-status] rect").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+pc.x,ib.y+pc.y);await p.waitForTimeout(3500);
  let t=await p.locator("#root").innerText();
  ok(t.includes("媒合狀態：先補資料")&&t.includes("推論（AI，未經 Owner 確認）"),"Eva explains the status and labels it as inference");
  ok(/主要用在哪裡/.test(t)&&t.includes("還不知道")&&t.includes("跳過"),"Eva asks ONE question (用途) with 還不知道 / 跳過");
  ok(!/推薦合作|RECOMMEND/.test(t),"no 推薦 shown");
  // answer 用途 → confirm → status stays 先補資料, next question is 可提供形式
  const box=p.locator("#chat-input, textarea").first();
  await box.click();await p.keyboard.type("做為長者共餐和課輔的場地");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(4000);
  t=await p.locator("#root").innerText();ok(t.includes("仍是 **先補資料**")||t.includes("仍是 先補資料"),"after 用途 only, status stays 先補資料 (one field is not enough)");
  ok(/可以用什麼形式提供/.test(t),"Eva asks the next question (可提供形式)");
  await box.click();await p.keyboard.type("活動中心可以借用，平日白天");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
  await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(5000);
  t=await p.locator("#root").innerText();ok(/先補資料 → 可探索/.test(t.replace(/\*/g,"")),"after both minimum fields: Eva says 先補資料 → 可探索 (by rule)");
  s=await pill();ok(s&&s.st==="EXPLORE"&&s.t.includes("可探索"),"the graph's status pill updates to 可探索");
  ok(t.includes("使用者陳述・未查證"),"answers are recorded as 使用者陳述・未查證");
  // 跳過 works and moves to another question
  await p.getByRole("button",{name:"跳過"}).last().click();await p.waitForTimeout(3000);t=await p.locator("#root").innerText();ok(t.includes("好，先跳過。"),"跳過 is accepted");
  // both-need line: 大庄 × 富琦 (B2 B7 both need)
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);await p.reload();await p.waitForTimeout(8000);
  await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
  const W2=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();await W2.selectOption('select[aria-label="分析專案"]',"48060125");await p.waitForTimeout(300);await W2.selectOption('select[aria-label="合作對象"]',"18706788");
  await W2.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const third=await G().evaluate(()=>[...document.querySelectorAll("[data-kv-third]")].map(x=>x.getAttribute("data-kv-third")).sort().join());
  ok(third.length>0,"both-need keys get a 共同尋找第三方 line ("+third+")");
  const both=await G().evaluate(()=>{const g=document.querySelector('[data-kv-role="both"]');return g?g.textContent:null});
  ok(both&&both.includes("需要＋能提供"),"大庄 B1 is drawn once as 需要＋能提供 (BOTH)");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
