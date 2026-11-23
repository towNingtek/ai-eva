// #234 手機媒合瀏覽器契約（iPhone 14，390×844）：真實 overlay（public/tangle-lab-overlay.js）＋ embed 頁
// （mode=match&v=live-match，補 match-task.js 與 match-cards.js，同 embed_route.py）。
// (a) 工作區開啟時頂端有「工作區｜對話」分頁，切換後另一側可見、兩者不重疊
// (b) 建議卡內每個文字元素右緣 ≤ 卡片右緣（卡片本身也不超出畫面）
// (c) 勾選列、卡片按鈕、確認框按鈕的可點區域皆 ≥ 44×44
// (d) 搜尋框輸入名稱後清單只剩符合項；名稱下一行顯示地點或主題
// (e) 收合鈕在畫面內、可點
// 自己伺服 repo；Playwright 由 NODE_PATH 提供（找不到時退回 /tmp/pw/node_modules）。最後一行 PASS。
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
let chromium;
try { ({chromium} = require('playwright')); } catch {
  try { ({chromium} = require('/tmp/pw/node_modules/playwright')); } catch {
    console.error('Playwright not found. Set NODE_PATH to a node_modules that has playwright.'); process.exit(2);
  }
}
const root = path.resolve(__dirname, '../..');
const add = (html, s) => html.replace(/<\/body>(?![\s\S]*<\/body>)/, s + '</body>');
const inject = html => {
  if (!html.includes('match-task.js')) html = add(html, '<script src="./match-task.js?v=live-match"></script>');
  if (!html.includes('match-cards.js')) html = add(html, '<script src="../tangle/match-cards.js?v=live-match"></script>');
  return html;
};
// 模擬 Chainlit 版面：頂端標題列、訊息區、底部輸入框（整頁高）。
const HOST = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>*{box-sizing:border-box}body{margin:0;font:14px system-ui}#root{height:100vh}
#app{display:flex;flex-direction:column;height:100%}#app header{height:60px;flex:none;border-bottom:1px solid #ddd;padding:18px}
#msgs{flex:1;overflow:auto;padding:12px}#chat-input{flex:none;margin:8px;height:44px}</style></head>
<body><div id="root"><div id="app"><header data-chat-header>Eva</header><div id="msgs" data-chat-messages><p>Eva：請在工作區選擇專案。</p></div>
<textarea id="chat-input" placeholder="輸入訊息"></textarea></div></div><script src="/public/tangle-lab-overlay.js"></script></body></html>`;
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); return res.end(HOST); }
  try {
    const file = path.join(root, decodeURIComponent(url.pathname));
    let bytes = await fs.readFile(file);
    if (url.pathname === '/public/workspace/embed.html' && url.searchParams.get('mode') === 'match'
        && url.searchParams.get('v') === 'live-match') bytes = inject(bytes.toString('utf8'));
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript; charset=utf-8' : file.endsWith('.html') ? 'text/html; charset=utf-8' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});

// 30 個專案：部分有地點／主題。
const PLACES = ['雲林縣斗六市', '雲林縣虎尾鎮', '嘉義縣竹崎鄉', '新竹縣竹北市', '台南市新化區'];
const TOPICS = ['農產通路', '社區照顧', '地方創生', '環境教育', '文化導覽'];
const NAMES = ['大庄社區', '農產合作社', '青年團隊', '導覽協會', '竹崎老街工作室', '竹北青農聯盟', '虎尾布袋戲', '斗六食農學堂',
  '新化老街', '海口漁村', '綠色隧道', '石榴班', '樟湖生態', '草嶺山城', '古坑咖啡', '西螺醬油', '北港糖廠', '麥寮海風',
  '口湖鰻魚', '台西蚵仔', '元長花生', '土庫菜市', '褒忠花卉', '東勢客家', '二崙西瓜', '崙背乳牛', '大埤酸菜', '莿桐蒜頭',
  '林內紫斑蝶', '水林番薯'];
const projects = NAMES.map((name, i) => ({uuid: `p${i}`, name,
  ...(i % 3 === 0 ? {location: PLACES[i % PLACES.length]} : {}), ...(i % 3 === 1 ? {topic: TOPICS[i % TOPICS.length]} : {})}));
const names = Object.fromEntries(projects.map(p => [p.uuid, p.name]));
const targets = ['p1', 'p2', 'p3'];
const KEYS = {B1: '空間與場域', B5: '人才與專業', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const result = {
  demo: false, note: '本次真實判斷（測試資料）', keys: KEYS, a: 'p0', not_evaluated: [],
  projects: ['p0', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'p0', pb, pair: ['p0', pb].sort().join('|'), status: 'EXPLORE', status_text: '可探索',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null})),
};
const LONG = 'https://example.org/very-long-unbroken-link-' + 'x'.repeat(80);
const NE = {'議題與目標對象': '未評估', '合作可執行性': '未評估', '跨國語境與成本': '未評估', '階段與時程': '未評估'};
const card = (rank, target) => ({
  rank, target, name: names[target] + '（' + '很長的專案全名'.repeat(4) + '）',
  fields: {
    '為何推薦': `符合規則「一方需要、另一方能提供」：大庄社區「需要行銷通路協助販售農產品」，${names[target]}「有通路可以協助販售」。`,
    '互補性': '一方有場地、一方有通路，雙方在農產品的販售與在地導覽上可以互相補位，形成穩定的合作關係。',
    '互惠價值': `雙方都能得到實際幫助。參考資料：${LONG}`, '建議合作': '先辦一場小型市集，再視成果決定是否擴大辦理。',
    '待確認': '市集預計在哪個月份？場地與人力由誰負責？', '風險': 'Timeline_mismatch_between_both_teams_may_delay_everything_' + 'y'.repeat(40),
  },
  '未評估': NE,
  '原文段落': [{'計畫': '大庄社區', '段落': 1, '原文': '需要行銷通路協助販售農產品' + LONG},
               {'計畫': names[target], '段落': 2, '原文': '有通路可以協助販售，也能提供導覽人力與場地。'}],
  '合作起步草案': null,
});
const cards = targets.map((t, i) => card(i + 1, t));

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  const W = 390, H = 844;
  try {
    const ctx = await browser.newContext({viewport: {width: W, height: H}, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'});
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(() => {
      window.events = [];
      window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); });
    });
    const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
    const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
    const evs = action => page.evaluate(action => events.filter(e => e.action === action), action);
    const base = {task_id: 'task-m', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null};
    const big = async (loc, what) => {
      const b = await loc.boundingBox();
      assert.ok(b, `${what} has a box`);
      assert.ok(b.width >= 44 - 0.01 && b.height >= 44 - 0.01, `${what} is ${b.width.toFixed(1)}×${b.height.toFixed(1)} (needs ≥ 44×44)`);
      return b;
    };
    // 某點最上層的元素（穿進工作區 iframe）是不是 sel。
    const topIs = (x, y) => page.evaluate(([x, y]) => {
      const el = document.elementFromPoint(x, y);
      return el ? (el.closest('#tangle-ws') ? 'ws' : el.closest('#tangle-ws-tabs') ? 'tabs' : el.closest('#root') ? 'chat' : el.tagName) : null;
    }, [x, y]);
    const rect = sel => page.evaluate(sel => { const r = document.querySelector(sel).getBoundingClientRect(); return {x: r.x, y: r.y, r: r.right, b: r.bottom}; }, sel);

    // ── (a) 分頁 ──
    await push({...base, status: 'loading'}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await page.waitForTimeout(500);  // 滑入動畫
    const bar = page.locator('#tangle-ws-tabs');
    ok(await bar.isVisible(), 'workspace open on a phone shows a tab bar at the top');
    const deskTab = bar.locator('[data-tws-tab="desk"]'), chatTab = bar.locator('[data-tws-tab="chat"]');
    const tabText = [await deskTab.textContent(), await chatTab.textContent()];
    ok(tabText.join('｜') === '工作區｜對話', `tabs read 工作區｜對話 (${tabText})`);
    const tb = await rect('#tangle-ws-tabs');
    ok(tb.y <= 0.5, 'tab bar sits at the top of the screen');
    ok(await deskTab.getAttribute('aria-selected') === 'true', 'workspace tab is selected when the workspace opens');
    const ws = await rect('#tangle-ws');
    ok(ws.x >= -0.5 && ws.r <= W + 0.5 && ws.r - ws.x >= W - 1, `workspace fills the phone width (${ws.x}–${ws.r})`);
    ok(ws.y >= tb.b - 0.5, 'tab bar does not cover the workspace');
    ok(!(await page.locator('#chat-input').isVisible()), 'chat is hidden behind the workspace tab (no overlap)');
    ok(await topIs(W / 2, H / 2) === 'ws' && await topIs(W / 2, H - 30) === 'ws', 'only the workspace is on screen in the workspace tab');
    await big(deskTab, 'workspace tab'); await big(chatTab, 'chat tab');

    await chatTab.click();
    await page.waitForTimeout(450);
    ok(await chatTab.getAttribute('aria-selected') === 'true', 'chat tab becomes selected');
    ok(await page.locator('#chat-input').isVisible() && !(await page.locator('#tangle-ws iframe').isVisible()), 'chat tab shows the chat and hides the workspace');
    const head = await rect('[data-chat-header]');
    ok(head.y >= tb.b - 0.5, 'chat header starts below the tab bar (no overlap)');
    ok(await topIs(W / 2, H / 2) === 'chat' && await topIs(20, (tb.b + head.b) / 2) === 'chat', 'only the chat is on screen in the chat tab');
    await deskTab.click();
    await page.waitForTimeout(450);
    ok(await page.locator('#tangle-ws iframe').isVisible() && !(await page.locator('#chat-input').isVisible()), 'workspace tab brings the workspace back');
    // ── (d) 搜尋 ＋ (c) 勾選列 ──
    await push({...base, status: 'select', projects, initiable: ['p0']});
    const search = panel.locator('[data-match-search]');
    await search.waitFor();
    const rows = panel.locator('[data-match-row]');
    ok(await rows.count() === 30, '30 projects listed');
    const sb = await search.boundingBox();
    const fb = await panel.locator('[data-match-row]').first().boundingBox();
    ok(sb.y + sb.height <= fb.y + 0.5, 'search box sits above the list');
    await big(search, 'search box');
    ok(await panel.locator('[data-match-row="p3"] [data-match-sub]').textContent() === PLACES[3 % 5], 'location shown under the name');
    ok(await panel.locator('[data-match-row="p1"] [data-match-sub]').textContent() === TOPICS[1], 'topic shown under the name');
    ok(await panel.locator('[data-match-row="p2"] [data-match-sub]').count() === 0, 'no sub-line when there is no location/topic');
    for (const id of ['p1', 'p5', 'p29']) await big(panel.locator(`[data-match-row="${id}"]`), `target row ${id}`);
    const rb = await panel.locator('[data-match-row="p1"]').boundingBox();
    ok(rb.x + rb.width <= W + 0.5, 'target rows fit on screen');
    // 整列可點：點名稱文字也會勾
    await panel.locator('[data-match-row="p1"] .mt-pick-name').click();
    ok(await panel.locator('[data-match-target="p1"]').isChecked(), 'tapping the row text ticks the target');
    await search.fill('竹');
    const visible = await rows.evaluateAll(rs => rs.filter(r => !r.hidden && r.offsetParent).map(r => r.dataset.matchRow));
    const want = projects.filter(p => p.name.includes('竹')).map(p => p.uuid);
    assert.deepEqual(visible, want);
    ok(want.length === 2, `search "竹" leaves only the matching names (${visible})`);
    await panel.locator('[data-match-row="p4"]').click();
    await panel.locator('[data-match-row="p5"]').click();
    await search.fill('');
    ok(await rows.evaluateAll(rs => rs.filter(r => !r.hidden).length) === 30, 'clearing the search shows the full list again');
    const ticked = await panel.locator('[data-match-target]:checked').evaluateAll(cs => cs.map(c => c.value));
    ok(ticked.join() === 'p1,p4,p5', `ticks survive filtering (${ticked})`);
    for (const b of await panel.locator('[data-match-task] button:visible').all()) await big(b, 'task panel button');
    await panel.locator('[data-match-start]').click();
    await page.waitForFunction(() => events.some(e => e.action === 'select'));
    assert.deepEqual((await evs('select'))[0].targets, ['p1', 'p4', 'p5']);
    ok(true, 'select sends the ticked targets');

    // ── (b) 建議卡 ＋ (c) 卡片／確認框按鈕 ──
    await push({...base, status: 'done', projects, a: 'p0', targets, result, cards,
      card_state: {}});
    await panel.locator('[data-match-card]').first().waitFor();
    for (const t of await panel.locator('[data-why-toggle]').all()) await t.click();  // 依據也展開一起量
    await page.waitForTimeout(200);
    const frame = page.frames().find(f => f.url().includes('/public/workspace/embed.html'));
    const over = await frame.evaluate(() => {
      const bad = [], vw = document.documentElement.clientWidth;
      for (const c of document.querySelectorAll('[data-match-card]')) {
        const cr = c.getBoundingClientRect();
        if (cr.right > vw + 0.5) bad.push(`card ${c.dataset.matchCard} right ${cr.right} > viewport ${vw}`);
        const walk = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
        let n, count = 0;
        while ((n = walk.nextNode())) {
          if (!n.textContent.trim()) continue;
          const r = document.createRange(); r.selectNodeContents(n);
          for (const q of r.getClientRects()) { count++; if (q.right > cr.right + 0.5) bad.push(`${n.parentElement.tagName}「${n.textContent.slice(0, 20)}」 ${q.right.toFixed(1)} > ${cr.right.toFixed(1)}`); }
        }
        for (const el of c.querySelectorAll('*')) {
          const r = el.getBoundingClientRect();
          if (r.width && r.right > cr.right + 0.5) bad.push(`<${el.tagName.toLowerCase()} class=${el.className}> ${r.right.toFixed(1)} > ${cr.right.toFixed(1)}`);
        }
        if (!count) bad.push('no text measured');
      }
      return bad;
    });
    assert.deepEqual(over, []);
    ok(true, 'every text element in every card stays inside the card (and the card inside the screen)');
    const dl = await frame.evaluate(() => {
      const dt = document.querySelector('[data-match-card] dt'), dd = dt.nextElementSibling;
      return dd.getBoundingClientRect().top >= dt.getBoundingClientRect().bottom - 0.5;
    });
    ok(dl, 'label and content stack top/bottom on a phone');
    const cardButtons = await panel.locator('[data-match-card] button').all();
    ok(cardButtons.length >= 5 * cards.length, `card buttons found (${cardButtons.length})`);
    for (const b of cardButtons) await big(b, `card button "${(await b.textContent()) || await b.getAttribute('data-label')}"`);
    ok(true, 'every card button is ≥ 44×44');
    await panel.locator('[data-match-card="p1"] [data-card-invite]').click();
    const dlg = panel.locator('[data-invite-confirm]');
    await dlg.waitFor();
    for (const sel of ['[data-invite-ok]', '[data-invite-cancel]']) await big(panel.locator(sel), `dialog ${sel}`);
    const box = await dlg.locator('> div').boundingBox();
    ok(box.x >= -0.5 && box.x + box.width <= W + 0.5, 'confirm dialog fits on screen');
    ok(true, 'confirm dialog buttons are ≥ 44×44');
    await panel.locator('[data-invite-cancel]').click();
    ok((await evs('invite')).length === 0, 'cancel sends no invite');

    // ── (e) 收合鈕 ──
    for (const tab of ['chat', 'desk']) {
      await bar.locator(`[data-tws-tab="${tab}"]`).click();
      await page.waitForTimeout(450);
      const c = page.locator('#tangle-ws-tabs [data-tws-close]');
      const b = await big(c, `collapse button (${tab} tab)`);
      ok(b.x >= 0 && b.y >= 0 && b.x + b.width <= W && b.y + b.height <= H, `collapse button is on screen in the ${tab} tab`);
      ok(await topIs(b.x + b.width / 2, b.y + b.height / 2) === 'tabs', `collapse button is not covered (${tab} tab)`);
    }
    await page.locator('#tangle-ws-tabs [data-tws-close]').click();
    await page.waitForTimeout(450);
    ok(!(await page.evaluate(() => window.__tangleWS.state.open)) && !(await bar.isVisible()), 'collapse closes the workspace and the tab bar');
    ok(await page.locator('#chat-input').isVisible() && await topIs(W / 2, H / 2) === 'chat', 'chat is back after collapsing');

    assert.deepEqual(errors, []);
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
