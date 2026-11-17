// Step D on the live lab (real mouse): ＋ 加入比較 → 3 / 4 plans → focus → per-pair status → walk into a pair with the right two plans.
// LAB_URL, LAB_PASS; Playwright via NODE_PATH. Last line "ALL OK <n>".
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();
  // two-plan default is unchanged: no extra selects until ＋ is pressed
  ok(await W.locator(".yl-extra select").count()===0&&await W.locator(".yl-add").isVisible(),"two-plan form unchanged, with a ＋ 加入比較 button");
  await W.selectOption('select[aria-label="分析專案"]',"48060125");await p.waitForTimeout(300);await W.selectOption('select[aria-label="合作對象"]',"85457156");
  await W.locator(".yl-add").click();await p.waitForTimeout(300);
  ok(await W.locator('select[aria-label="比較對象 3"]').count()===1,"＋ adds 比較對象 3");
  await W.selectOption('select[aria-label="比較對象 3"]',"15080750");
  await W.locator(".yl-add").click();await p.waitForTimeout(300);
  ok(await W.locator('select[aria-label="比較對象 4"]').count()===1&&await W.locator(".yl-add").isDisabled(),"second ＋ adds 比較對象 4, then the button is disabled (max 4)");
  await W.locator('button[aria-label="移除比較對象 4"]').click();await p.waitForTimeout(300);
  ok(await W.locator('select[aria-label="比較對象 4"]').count()===0,"移除 removes 比較對象 4");
  const title=await W.locator("#deskTitle").textContent();ok(title.includes("大庄")&&title.includes("林中")&&title.includes("水尾"),"title lists the 3 plans");
  await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(7000);
  const G=()=>p.frames().filter(f=>f.url().includes("tangle-match")).pop();
  const pl=await G().evaluate(()=>P.map(x=>x.pid).join());ok(pl==="48060125,85457156,15080750","graph shows the 3 plans ("+pl+")");
  const opened=(await p.locator("#root").innerText()).split("已開啟").pop();ok(opened.includes("大庄")&&opened.includes("林中")&&opened.includes("水尾"),"Eva's 已開啟 message names all 3 plans");
  ok(await G().evaluate(()=>!document.querySelector("[data-mf-status]")),"not focused: no status labels");
  // focus 大庄 with a real click
  const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
  const c0=await G().evaluate(()=>{const id=P[0].id,a=pos[id],m=document.getElementById('svg').getScreenCTM();return{x:a.x*m.a+m.e,y:a.y*m.d+m.f}});
  await p.mouse.click(ib.x+c0.x,ib.y+c0.y);await p.waitForTimeout(3500);
  const st=await G().evaluate(()=>[...document.querySelectorAll("[data-mf-status]")].map(g=>g.getAttribute("data-mf-pair")+"="+g.textContent));
  ok(st.length===2,"focused: one status per other plan ("+st.join(" ; ")+")");
  let t=await p.locator("#root").innerText();
  ok(t.includes("和 **")===false&&/和 .*林中.*互補候選/.test(t)&&/和 .*水尾.*互補候選/.test(t),"Eva lists matches with each of the other two plans");
  // click the 大庄 × 水尾 status → Eva explains that pair
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height-15);await p.waitForTimeout(300);
  const sc=await G().evaluate(()=>{const g=[...document.querySelectorAll("[data-mf-status]")].find(x=>x.getAttribute("data-mf-pair").includes("15080750"));const r=g.querySelector("rect").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+sc.x,ib.y+sc.y);await p.waitForTimeout(3500);t=await p.locator("#root").innerText();
  ok(/媒合狀態：(先補資料|可探索)/.test(t),"clicking a pair status: Eva explains that pair's status");
  // walk into a pair: 大庄 B2 need ← 水尾 B2 offer
  const sat=await G().evaluate(()=>{const g=document.querySelector('[data-kv-key="B2"][data-kv-owner="48060125"]');const r=g.querySelector("image").getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+sat.x,ib.y+sat.y);await p.waitForTimeout(3500);
  const own=await G().evaluate(()=>[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-owner")).sort().join());
  ok(own==="15080750,48060125","walk-in shows 大庄 × 水尾 (the plan that offers B2)");
  t=await p.locator("#root").innerText();ok(t.includes("B2 產品與生產")&&t.includes("互補候選")&&t.includes("水尾"),"Eva answers for 大庄 × 水尾 B2");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
