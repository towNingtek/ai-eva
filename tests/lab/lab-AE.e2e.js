// A + E on the live lab (real mouse). LAB_URL, LAB_PASS; Playwright via NODE_PATH. Last line "ALL OK <n>".
// A: reloading never stacks "要繼續分析嗎？" — exactly one, and its buttons work.
// E: typing with no satellite selected gets the fixed "no AI" note (server must not call the AI); with a satellite, the supplement flow is unchanged.
const{execSync}=require("child_process");
let chromium;try{({chromium}=require("playwright"))}catch(e){console.error("Playwright not found. Set NODE_PATH.");process.exit(2)}
const U=process.env.LAB_URL||"http://127.0.0.1:7863",PW=process.env.LAB_PASS;
let n=0;const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);n++;console.log("ok",m)};
const logMark=()=>+execSync("docker logs ai-eva-tangle-lab 2>&1 | wc -l").toString().trim();
const logSince=m=>execSync(`docker logs ai-eva-tangle-lab 2>&1 | tail -n +${m+1}`).toString();
(async()=>{if(!PW){console.error("LAB_PASS not set");process.exit(2)}
 const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
 try{
  await p.goto(U+"/");await p.waitForTimeout(1500);
  await p.locator('input[type="text"],input#email,input[type="email"]').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(6000);
  const prompts=async()=>(await p.locator("#root").innerText()).split("要繼續分析嗎？").length-1;
  await p.getByRole("button",{name:/⚖ 法規檢核/}).last().click();await p.waitForTimeout(5000);await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);
  for(let i=1;i<=3;i++){await p.reload();let c=0;for(let k=0;k<40;k++){await p.waitForTimeout(500);c=await prompts();if(c>=1&&k>=12)break}ok(await prompts()===1,`A: after reload ${i}, exactly one 要繼續分析嗎？ (${await prompts()})`)}
  await p.getByRole("button",{name:/⚖ 法規檢核/}).last().click();await p.waitForTimeout(5000);
  ok(await p.evaluate(()=>document.body.classList.contains("tangle-ws-on")),"A: the remaining prompt's button opens the workspace");
  await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1500);
  // E: nothing selected -> fixed note, no AI call on the server
  let mark=logMark();const box=p.locator("#chat-input, textarea").first();
  await box.click();await p.keyboard.type("你好，請問大庄的計畫重點是什麼？");await p.keyboard.press("Enter");await p.waitForTimeout(6000);
  let t=await p.locator("#root").innerText();ok(t.includes("試作環境沒有接 AI"),"E: plain chat gets the fixed 試作環境沒有接 AI note");
  const log=logSince(mark);ok(!/chat\/completions|Connection error|Traceback/.test(log),"E: no AI request, connection error or traceback on the server");
  // E: with a satellite selected, the supplement flow still works
  await p.getByRole("button",{name:/⚖ 法規檢核/}).last().click();await p.waitForTimeout(5000);
  const W=p.frames().filter(f=>f.url().includes("/public/workspace/embed.html")).pop();await W.selectOption('select[aria-label="分析專案"]',"48060125");
  await W.locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(6000);
  const G=p.frames().filter(f=>f.url().includes("tangle-law")).pop();await G.evaluate(()=>{orbitPaused=true});
  const ib=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();await p.mouse.move(ib.x+20,ib.y+40);await p.waitForTimeout(200);
  const c=await G.evaluate(()=>{const r=document.querySelector('[data-kv-key="開發審議"] image').getBoundingClientRect();return{x:r.x+r.width/2,y:r.y+r.height/2}});
  await p.mouse.click(ib.x+c.x,ib.y+c.y);await p.waitForTimeout(3000);
  await box.click();await p.keyboard.type("基地約 0.4 公頃");await p.keyboard.press("Enter");await p.waitForTimeout(3500);
  t=await p.locator("#root").innerText();ok(t.includes("確認補充到「開發審議"),"E: with a satellite selected, typing still becomes a supplement draft");
  await p.getByRole("button",{name:"取消"}).last().click();await p.waitForTimeout(1500);
  ok(errs.length===0,"no page errors"+(errs.length?": "+errs.join(";"):""));
  console.log("ALL OK",n);
 }finally{await b.close()}
})().catch(e=>{console.error(e.message);process.exit(1)});
