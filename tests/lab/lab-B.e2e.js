// Step B on the live lab (real mouse): walk into a need×offer pair, a peer pair, and click a planet.
// LAB_URL, LAB_PASS; Playwright via NODE_PATH. Last line "ALL OK <n>".
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  const openPair=async(a,c)=>{await p.getByRole("button",{name:/🤝 媒合分析/}).last().click();await p.waitForTimeout(5000);
   const W=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();await W.selectOption('select[aria-label="分析專案"]',a);await p.waitForTimeout(300);await W.selectOption('select[aria-label="合作對象"]',c);
   await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
   return{G:p.frames().filter(f=>f.url().includes("tangle-match")).pop(),ib:await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox()}};
  const chat=()=>p.locator("#root").innerText();
  // 林中 × 水尾: B1 空間與場域 (林中 need, 水尾 offer)
  let {G,ib}=await openPair("85457156","15080750");
  await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height/2);await p.waitForTimeout(300);
  let c=await G.evaluate(()=>{const r=document.querySelector('[data-kv-key="B1"][data-kv-owner="85457156"] image').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+c.x,ib.y+c.y);await p.waitForTimeout(3000);
  let v=await G.evaluate(()=>({f:[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-role")).sort().join(),pts:PT.length}));
  ok(v.f==="need,offer","clicking 林中 空間與場域・需要 walks into the pair (need + offer)");
  ok(v.pts===3,"the pair route carries 3 flow particles");
  let t=await chat();ok(t.includes("改善公共空間與基礎環境")&&t.includes("整修社區活動中心"),"Eva quotes both sides of the pair");
  ok(t.includes("互補候選")&&t.includes("示範"),"Eva says 互補候選 (standard v1.1) and marks it as demo");
  await p.frameLocator("#tangle-ws iframe").frameLocator("iframe.original-tangle").locator("#mfBack").click();await p.waitForTimeout(1500);
  ok(await G.evaluate(()=>!document.querySelector("[data-mf-focus]")),"← 返回兩個星系 leaves the pair view");
  // planet click: original focus + Eva summary
  const pl=await G.evaluate(()=>{const i=[...document.querySelectorAll('#svg image')].sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width)[0].getBoundingClientRect();return{x:i.x+i.width/2,y:i.y+i.height/2,w:i.width}});
  await p.mouse.click(ib.x+pl.x,ib.y+pl.y);await p.waitForTimeout(3000);
  const pf=await G.evaluate(()=>({focus,w:[...document.querySelectorAll('#svg image')].sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width)[0].getBoundingClientRect().width}));
  ok(pf.focus&&pf.w>pl.w*1.08,`clicking a planet still does the original focus (${pl.w.toFixed(0)}→${pf.w.toFixed(0)}px)`);
  t=await chat();ok(t.includes("B1–B8")&&t.includes("**需要**")===false&&/需要：/.test(t)&&/互補候選 \d+ 條/.test(t),"Eva lists the planet's B1–B8 needs / offers and how many 互補候選 (standard v1.1)");
  // peer pair: 大庄 × 大德, B6 社群與關係 both offer
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);await p.reload();await p.waitForTimeout(7000);
  ({G,ib}=await openPair("48060125","26791874"));await p.mouse.move(ib.x+ib.width/2,ib.y+ib.height/2);await p.waitForTimeout(300);
  const m=await G.evaluate(()=>{const pth=document.querySelector('[data-kv-peer="B6"]'),pt=pth.getPointAtLength(pth.getTotalLength()*.5),mm=pth.getScreenCTM();return{x:pt.x*mm.a+mm.e,y:pt.y*mm.d+mm.f}});
  await p.mouse.click(ib.x+m.x,ib.y+m.y);await p.waitForTimeout(3000);
  v=await G.evaluate(()=>({f:[...document.querySelectorAll("[data-mf-focus]")].map(g=>g.getAttribute("data-mf-role")).join(),pts:PT.length,cap:(document.querySelector("[data-mf-caption]")||{}).textContent||""}));
  ok(v.f==="offer,offer"&&v.pts===0&&v.cap.includes("可聯合或交流"),"clicking the peer line walks into a both-offer pair with no flow");
  await p.keyboard.press("Escape");await p.waitForTimeout(1500);G=p.frames().filter(f=>f.url().includes("tangle-match")).pop();ok(await G.evaluate(()=>!document.querySelector("[data-mf-focus]")),"Esc leaves the pair view");
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
