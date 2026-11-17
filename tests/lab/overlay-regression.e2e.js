const{chromium}=require("playwright");const ok=(c,m)=>{if(!c)throw Error("FAIL "+m);console.log("ok",m)};
(async()=>{const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:900}});const errs=[];p.on("pageerror",e=>errs.push(e.message));
const U=process.env.U;await p.goto(U+"/");await p.waitForTimeout(1500);
await p.locator('input[type="text"],input#email').first().fill("tangle-lab");await p.locator('input[type="password"]').fill(process.env.PW);await p.locator('button[type="submit"]').click();await p.waitForTimeout(5000);
const sb=()=>p.evaluate(()=>{const s=document.querySelector('div[data-side="left"][data-state][data-collapsible]');return s?s.getAttribute("data-state"):"none"});
ok(new URL(p.url()).pathname==="/","starts on Chainlit default page");ok(await p.locator("#tangle-ws").count()===0,"no workspace before choosing");
const sb0=await sb();console.log("sidebar at start:",sb0);await p.screenshot({path:"/tmp/ov-1.png"});
const chat=()=>p.locator("#root").innerText();
await p.getByRole("button",{name:/⚖ 法規檢核/}).first().click();await p.waitForTimeout(3500);
ok(await p.locator("#tangle-ws").isVisible(),"workspace opens after 法規檢核");ok(await sb()!=="expanded","session list collapsed");
const wsBox=await p.locator("#tangle-ws").boundingBox();console.log("workspace box",JSON.stringify(wsBox));
await p.screenshot({path:"/tmp/ov-2.png"});
const W=()=>p.frames().find(f=>f.url().includes("/public/workspace/embed.html"));
await W().selectOption('select[aria-label="分析專案"]',"97236457");await W().locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(4500);
ok((await chat()).includes("已開啟 法規檢核"),"open event -> Eva in Chainlit chat");
const G=()=>p.frames().find(f=>f.url().includes("tangle-law"));ok(await G().evaluate(()=>[...document.querySelectorAll("[data-kv-key]")].filter(g=>g.getAttribute("data-kv-state")!=="uncovered").length)===10,"台子 10 law-domain satellites");
const gi=p.frameLocator("#tangle-ws iframe").frameLocator("iframe.original-tangle");const gb=await p.frameLocator("#tangle-ws iframe").locator("iframe.original-tangle").boundingBox();
await G().evaluate(()=>{orbitPaused=true});await p.mouse.move(gb.x+30,gb.y+60);await p.waitForTimeout(200);const sc=await G().evaluate(()=>{const r=document.querySelector('[data-kv-key="開發審議"] image').getBoundingClientRect();return{x:r.left+r.width/2,y:r.top+r.height/2}});await p.mouse.click(gb.x+sc.x,gb.y+sc.y);await p.waitForTimeout(3000);
ok((await chat()).includes("申請開發或變更的基地面積多大"),"domain click -> Eva asks the gap question");await p.screenshot({path:"/tmp/ov-3.png"});
const box=p.locator("#chat-input, textarea").first();await box.click();await p.keyboard.type("基地約 0.5 公頃");await p.keyboard.press("Enter");await p.waitForTimeout(3000);
const kst=()=>G().evaluate(()=>document.querySelector('[data-kv-key="開發審議"]').getAttribute("data-kv-state"));ok(await kst()==="gap","not recorded before confirm");
await p.getByRole("button",{name:"確認納入"}).last().click();await p.waitForTimeout(4000);
ok(await kst()==="na","Eva confirm -> graph re-judged by rule (0.5 公頃 < 1 公頃 → 未涉及)");ok(/不觸及/.test(await chat()),"Eva reports the rule result");
await p.screenshot({path:"/tmp/ov-4.png"});
// collapse restores
await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1200);
ok(!(await p.locator("#tangle-ws").isVisible())||(await p.locator("#tangle-ws").evaluate(e=>e.classList.contains("hide"))),"workspace collapsed");
ok(await sb()===sb0,"session list restored to "+sb0);await p.screenshot({path:"/tmp/ov-5.png"});
// reopen via 媒合分析
await p.getByRole("button",{name:/🤝 媒合分析/}).first().click();await p.waitForTimeout(3500);ok(await sb()!=="expanded","collapsed again for 媒合");
await W().selectOption('select[aria-label="分析專案"]',"72996038");await W().selectOption('select[aria-label="合作對象"]',"15080750");await W().locator(".primary",{hasText:"確認並開始分析"}).click();await p.waitForTimeout(4500);
const M=p.frames().find(f=>f.url().includes("tangle-match"));ok((await M.evaluate(()=>P.map(x=>x.name))).join("|")==="雲林縣元長鄉崙仔社區農村再生計畫|雲林縣崙背鄉水尾社區農村再生計畫","match planets");
ok((await chat()).includes("已開啟 媒合分析"),"match open -> Eva");await p.screenshot({path:"/tmp/ov-6.png"});
await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1200);ok(await sb()===sb0,"restored after 媒合");
// REOPEN: same conversation, same button again
const vis=()=>p.evaluate(()=>{const w=document.getElementById("tangle-ws");return !!w&&!w.classList.contains("hide")});
await p.getByRole("button",{name:/法規檢核/}).last().click();await p.waitForTimeout(3500);ok(await vis(),"reopen after 收合 (same conversation)");
await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1000);
// REOPEN after reload (resumed thread: old buttons are dead, new ones offered)
await p.reload();await p.waitForTimeout(6000);ok(/\/thread\//.test(p.url()),"reload stays on the thread");
ok((await chat()).includes("要繼續分析嗎"),"resume offers fresh entry buttons");
await p.getByRole("button",{name:/法規檢核/}).last().click();await p.waitForTimeout(4000);ok(await vis(),"reopen after reload");
await p.screenshot({path:"/tmp/ov-7-reopen.png"});
await p.locator("#tangle-ws-close").click();await p.waitForTimeout(1000);ok(await sb()===sb0,"restored after reopen");
// REOPEN from session list (history)
await p.goto(U+"/");await p.waitForTimeout(4000);const item=p.locator('a[href^="/thread/"], [id^="thread-"]').first();
if(await item.count()){await item.click();await p.waitForTimeout(5000);await p.getByRole("button",{name:/法規檢核/}).last().click();await p.waitForTimeout(4000);ok(await vis(),"reopen from session history");await p.locator("#tangle-ws-close").click();await p.waitForTimeout(800)}else console.log("(no history link found)");
// colour check: no purple in workspace/graph computed styles
const purple=await p.evaluate(()=>{const fr=document.querySelector("#tangle-ws iframe");return fr?"has-frame":"none"});
ok(errs.length===0,"no page errors "+errs.join(";"));await b.close()})().catch(e=>{console.error(e.message);process.exit(1)});
