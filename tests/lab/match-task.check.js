// #203 真實媒合任務瀏覽器契約：工具區開啟 → 接回任務 → 選 A × 2–4 → 真實結果套原畫法
// （B1–B8 衛星、月牙＝需要、互補光流、走進一對）→ 2–4 案比較 → 點衛星送出說明事件。
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
// 與 app/apps/match_analysis/embed_route.py 相同的規則：只有 mode=match&v=live-match 才補 match-task.js。
const inject = html => html.includes('match-task.js') ? html
  : html.replace(/<\/body>(?![\s\S]*<\/body>)/, '<script src="./match-task.js?v=live-match"></script></body>');
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') {
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><body><div id="root"></div><script src="/public/tangle-lab-overlay.js"></script></body>');
  }
  try {
    const file = path.join(root, decodeURIComponent(url.pathname));
    let bytes = await fs.readFile(file);
    if (url.pathname === '/public/workspace/embed.html' && url.searchParams.get('mode') === 'match'
        && url.searchParams.get('v') === 'live-match') bytes = inject(bytes.toString('utf8'));
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});

const KEYS = {B1:'空間與場域',B2:'產品與生產',B3:'服務與體驗',B4:'內容與品牌',B5:'人才與專業',B6:'社群與關係',B7:'市場與通路',B8:'治理與平台'};
const ids = ['live-a', 'live-b', 'live-c', 'live-d', 'live-e'];
const names = {'live-a':'真實 A 案','live-b':'真實 B 案','live-c':'真實 C 案','live-d':'真實 D 案','live-e':'真實 E 案'};
const roles = {
  'live-a': {B2:'need', B4:'offer', B6:'both', B7:'need'},
  'live-b': {B2:'offer', B7:'offer', B5:'need'},
  'live-c': {B4:'need', B6:'offer', B1:'offer'},
  'live-d': {B7:'need', B8:'offer'},
  'live-e': {B3:'offer', B2:'offer'},
};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k =>
  [k, {role: roles[pid][k] || 'none', evidence: roles[pid][k] ? [`${names[pid]}原文：${KEYS[k]}`] : []}]))});
const projects = ids.map(uuid => ({uuid, name: names[uuid]}));
const targets = ['live-b', 'live-c', 'live-d', 'live-e'];
// 伺服器狀態故意與頁面規則不同（A×B 有互補、規則會算「先補資料」；伺服器給「可探索」），用來確認畫面吃的是伺服器結果。
const STATUS = {'live-b':['EXPLORE','可探索'],'live-c':['CLARIFY_FIRST','先補資料'],'live-d':['CLARIFY_FIRST','先補資料'],'live-e':['ELIGIBLE','可排序・未建議']};
const result = {
  demo: false, note: '本次真實判斷（測試資料）', keys: KEYS, a: 'live-a', not_evaluated: [],
  projects: ['live-a', ...targets].map(side),
  pairs: targets.map((pb, i) => ({pa:'live-a', pb, pair:['live-a', pb].sort().join('|'), status: STATUS[pb][0], status_text: STATUS[pb][1],
    relations: {}, counts: {complement: 2 - (i % 2), third: i === 2 ? 1 : 0, peer: i === 1 ? 1 : 0}, next_question: null})),
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
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
    const waitAction = (action, n = 1) => page.waitForFunction(([a, n]) => events.filter(e => e.action === a).length >= n, [action, n]);
    const base = {task_id: 'task-1', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null};

    // 1. 工具區開啟（opening，不帶 update）→ 工作區自己送 get 接回任務
    await push({...base, status: 'loading'}, false);
    assert.match(await page.locator('#tangle-ws iframe').getAttribute('src'), /mode=match&v=live-match/);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await waitAction('get');
    ok((await evs('get'))[0].kind === 'match_task', 'panel asks the server for the current task on open (reconnect, no rerun)');
    ok(await panel.locator('.desk-foot').isHidden(), 'demo desk footer is replaced by the live task');

    // 2. 選 A 與 2–4 個對象
    await push({...base, status: 'select', projects});
    await panel.locator('[data-match-a]').selectOption('live-a');
    ok(await panel.locator('[data-match-target="live-a"]').isDisabled(), 'A cannot also be a target');
    const start = panel.locator('[data-match-start]');
    await panel.locator('[data-match-target="live-b"]').check();
    ok(await start.isDisabled(), 'one target is not enough (needs 2–4)');
    for (const t of targets.slice(1)) await panel.locator(`[data-match-target="${t}"]`).check();
    ok(!(await start.isDisabled()), 'four targets can start');
    await start.click();
    await waitAction('select');
    assert.deepEqual((await evs('select'))[0], {kind: 'match_task', action: 'select', task_id: 'task-1', a: 'live-a', targets});
    ok(true, 'select event carries A and the 4 targets with the task id');

    // 3. 判斷中 → 完成（真實結果）
    await push({...base, status: 'running', projects, a: 'live-a', targets, progress: [{uuid: 'live-a', name: names['live-a'], step: 'fetch'}]});
    await panel.getByText('正在判斷各案的需要／能提供…').waitFor();
    const done = {...base, status: 'done', projects, a: 'live-a', targets, result};
    await push(done);
    await panel.getByText('媒合判斷完成').waitFor();

    // 4. 2–4 案比較
    const rows = panel.locator('[data-match-compare] tbody tr');
    await rows.first().waitFor();
    ok(await rows.count() === 4, 'comparison lists all 4 A × target pairs');
    const statuses = await rows.evaluateAll(trs => trs.map(tr => tr.children[1].textContent));
    assert.deepEqual(statuses, targets.map(t => STATUS[t][1]));
    ok(true, 'comparison shows the server status of each pair');

    // 5. 真實資料套原畫法
    const frameEl = panel.locator('iframe[data-match-galaxy]');
    assert.match(await frameEl.getAttribute('src'), /liveMatch=1.*ps=live-a,live-b,live-c,live-d$/);
    const G = () => page.frames().filter(f => f.url().includes('tangle-match.html?liveMatch=1')).pop();
    await (async () => { for (let i = 0; i < 50 && !G(); i++) await page.waitForTimeout(100); })();
    await G().waitForFunction(() => typeof P !== 'undefined' && document.querySelectorAll('[data-kv-key]').length > 0);
    ok(await G().evaluate(() => P.map(p => p.pid).join()) === 'live-a,live-b,live-c,live-d', 'galaxy draws A + 3 real projects (layout max 4)');
    ok(await G().evaluate(() => KV_MATCH.demo === false && !('48060125' in KV_MATCH.projects)), 'demo data replaced by the real result');
    const sats = await G().evaluate(() => [...document.querySelectorAll('[data-kv-key]')].map(g => ({k: g.dataset.kvKey, owner: g.dataset.kvOwner, role: g.dataset.kvRole, shadow: !!g.querySelector('[data-need-shadow]')})));
    for (const pid of ['live-a', 'live-b', 'live-c', 'live-d']) {
      const want = Object.keys(roles[pid]).sort().join();
      const got = sats.filter(s => s.owner === pid).map(s => s.k).sort().join();
      assert.equal(got, want, `${pid} satellites`);
      for (const s of sats.filter(s => s.owner === pid)) assert.equal(s.role, roles[pid][s.k], `${pid} ${s.k} role`);
    }
    ok(true, 'B1–B8 satellites per planet follow the real need/offer roles');
    const needs = sats.filter(s => ['need', 'both'].includes(s.role));
    ok(needs.length > 0 && needs.every(s => s.shadow) && sats.filter(s => s.role === 'offer').every(s => !s.shadow), 'crescent shadow marks every need (and only needs)');
    ok(await G().evaluate(() => TRACKS.some(t => !t.peer && P.find(p => p.id === t.from).pid === 'live-b' && P.find(p => p.id === t.to).pid === 'live-a' && t.tag === 'B2')),
      'complementary flow route B offers B2 → A needs B2');
    await G().waitForFunction(() => typeof PT !== 'undefined' && PT.length > 0, null, {timeout: 8000});
    const u0 = await G().evaluate(() => PT.map(q => q.u));
    await page.waitForTimeout(800);
    const u1 = await G().evaluate(() => PT.map(q => q.u));
    ok(u0.length > 0 && u1.some((u, i) => u !== u0[i]), `light-flow particles move (${u0.length})`);
    await G().waitForFunction(() => window.mfStatusPair(P[0], P[1]) === 'EXPLORE');
    ok(await G().evaluate(() => window.mfStatusPair(P[0], P[2]) === 'CLARIFY_FIRST'), 'per-pair status comes from the server result');

    // 6. 點衛星：走進一對 + 送出說明事件（不重判）
    const before = (await evs('explain')).length;
    await G().evaluate(() => {
      const sg = document.querySelector('[data-kv-key="B2"][data-kv-owner="live-a"]');
      const t = sg.parentNode.querySelector('[data-dd-satellite="B2"]');
      t.onkeydown({key: 'Enter', type: 'keydown', stopPropagation() {}, preventDefault() {}});
    });
    await G().waitForFunction(() => document.querySelectorAll('[data-mf-focus]').length > 0);
    const own = await G().evaluate(() => [...new Set([...document.querySelectorAll('[data-mf-focus]')].map(g => g.getAttribute('data-mf-owner')))].sort().join());
    ok(own === 'live-a,live-b', `walk into a pair shows A and its B2 provider (${own})`);
    await waitAction('explain', before + 1);
    const ex = (await evs('explain'))[before];
    assert.equal(ex.kind, 'pair');
    assert.equal(ex.code, 'B2');
    assert.equal(ex.task_id, 'task-1');
    assert.equal(ex.pa, 'live-a');
    assert.equal(ex.who, 'live-a');
    ok(true, 'satellite click sends match_task explain {code:B2, pa:A, task_id}');
    ok((await evs('select')).length === 1, 'explaining does not resend select (no re-judging)');

    // 7. 第 4 個對象可以換進星圖
    await panel.locator('[data-match-show="live-e"]').click();
    await page.waitForFunction(() => {
      const f = document.querySelector('#tangle-ws iframe').contentDocument.querySelector('iframe[data-match-galaxy]');
      return f && f.src.includes('live-e');
    });
    ok(/ps=live-a,live-[bcd],live-[bcd],live-e$/.test(await frameEl.getAttribute('src')), 'the 4th target can be swapped into the galaxy');

    // 8. 返回同一對話：接回原任務、不重跑
    const selects = (await evs('select')).length, news = (await evs('new')).length;
    await push(done, false);
    await panel.getByText('媒合判斷完成').waitFor();
    ok((await evs('select')).length === selects && (await evs('new')).length === news, 're-entering the same task sends no select/new');

    // 9. 只有「開始新媒合」才建新任務
    await panel.locator('[data-match-new]').click();
    await waitAction('new');
    assert.deepEqual((await evs('new'))[0], {kind: 'match_task', action: 'new', task_id: 'task-1'});
    await push({...base, task_id: 'task-2', status: 'select', projects});
    await panel.locator('[data-match-start]').waitFor();
    ok(!(await panel.locator('iframe[data-match-galaxy]').count()), 'new task clears the old galaxy');
    await push({...base, task_id: 'task-2', status: 'error', projects, error: '讀取專案清單失敗（CMS 503）'});
    await panel.getByText('讀取專案清單失敗（CMS 503）').waitFor();
    ok(true, 'errors are shown as sent by the server');

    // 10. 示範／雲林的專案媒合原樣
    await call({mode: 'match'});
    await page.waitForFunction(() => /mode=match&v=1/.test(document.querySelector('#tangle-ws iframe').getAttribute('src')));
    await panel.locator('#deskTitle').getByText(/媒合分析/).waitFor();
    ok(await panel.locator('[data-match-task]').count() === 0, 'demo match workspace (no live-match) is unchanged');
    const demo = await browser.newPage();
    await demo.goto(`http://127.0.0.1:${server.address().port}/public/tangle/tangle-match.html`);
    await demo.waitForFunction(() => typeof P !== 'undefined');
    ok(await demo.evaluate(() => KV_MATCH.demo === true && P.length === 2 && !document.documentElement.dataset.liveMatch), 'tangle-match.html without liveMatch keeps demo data');
    await demo.close();

    assert.deepEqual(errors, []);
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
