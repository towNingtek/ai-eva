// #215 媒合流程瀏覽器契約：判斷完成 → 任務面板出 3 張建議卡（為何推薦＋原文段落、無 B 代號）
// → 收藏送 card_action → 寄站內邀請先出確認框（取消不送、確定才送 invite confirmed:true）。
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
// 與 app/apps/match_analysis/embed_route.py 相同的規則：mode=match&v=live-match 才補 match-task.js 與 match-cards.js。
const add = (html, s) => html.replace(/<\/body>(?![\s\S]*<\/body>)/, s + '</body>');
const inject = html => {
  if (!html.includes('match-task.js')) html = add(html, '<script src="./match-task.js?v=live-match"></script>');
  if (!html.includes('match-cards.js')) html = add(html, '<script src="../tangle/match-cards.js?v=live-match"></script>');
  return html;
};
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

const names = {a: '大庄社區', b: '農產合作社', c: '青年團隊', d: '導覽協會'};
const targets = ['b', 'c', 'd'];
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const KEYS = {B1: '空間與場域', B5: '人才與專業', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const result = {
  demo: false, note: '本次真實判斷（測試資料）', keys: KEYS, a: 'a', not_evaluated: [],
  projects: ['a', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: 'EXPLORE', status_text: '可探索',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null})),
};
const NE = {'議題與目標對象': '未評估', '合作可執行性': '未評估', '跨國語境與成本': '未評估', '階段與時程': '未評估'};
const card = (rank, target) => ({
  rank, target, name: names[target],
  fields: {
    '為何推薦': `符合規則「一方需要、另一方能提供」：大庄社區「需要行銷通路協助販售農產品」，${names[target]}「有通路可以協助販售」。`,
    '互補性': '一方有場地、一方有通路。', '互惠價值': '雙方都能得到實際幫助。', '建議合作': '先辦一場小型市集。',
    '待確認': '市集預計在哪個月份？', '風險': '時程可能不同步。',
  },
  '未評估': NE,
  '原文段落': [{'計畫': '大庄社區', '段落': 1, '原文': '需要行銷通路協助販售農產品'},
               {'計畫': names[target], '段落': 1, '原文': '有通路可以協助販售'}],
  '合作起步草案': null,
});
const cards = targets.map((t, i) => card(i + 1, t));

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
    const base = {task_id: 'task-1', projects, a: 'a', targets, min_targets: 2, max_targets: 4, progress: [], error: null,
                  cards: [], card_state: {}};

    await push({...base, status: 'loading', result: null}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await push({...base, status: 'running', result: null});
    ok(await panel.locator('[data-match-card]').count() === 0, 'no cards while judging');

    // 1. 判斷完成 → 3 張建議卡
    const done = {...base, status: 'done', result, cards};
    await push(done);
    await panel.getByText('媒合判斷完成').waitFor();
    const cardEls = panel.locator('[data-match-cards] [data-match-card]');
    await cardEls.first().waitFor();
    ok(await cardEls.count() === 3, '3 suggestion cards shown');
    ok(JSON.stringify(await cardEls.evaluateAll(els => els.map(e => e.dataset.matchCard))) === JSON.stringify(targets), 'cards follow the server ranking');
    for (let i = 0; i < 3; i++) {
      const c = cardEls.nth(i);
      const why = await c.locator('[data-field="為何推薦"]').textContent();
      assert.ok(why.includes('一方需要、另一方能提供'), 'why shows the rule');
      assert.ok((await c.locator('[data-why-quotes]').textContent()).includes('需要行銷通路協助販售農產品'), 'why shows the original text');
      assert.match(await c.locator('[data-not-evaluated]').textContent(), /未評估/);
      for (const label of ['收藏', '略過', '補資料', '寄站內邀請']) assert.equal(await c.getByRole('button', {name: label}).count(), 1, label);
    }
    ok(true, 'each card has 為何推薦 (rule + original text), 未評估, and the 4 buttons');
    const text = await panel.locator('[data-match-cards]').textContent();
    ok(!/\bB[1-8]\b/.test(text), 'cards show no B codes');

    // 2. 收藏 → card_action
    await cardEls.nth(0).getByRole('button', {name: '收藏'}).click();
    await waitAction('card_action');
    assert.deepEqual((await evs('card_action'))[0], {kind: 'match_task', action: 'card_action', task_id: 'task-1', op: 'favorite', target: 'b'});
    ok(true, '收藏 sends card_action {op:favorite, target}');

    // 3. 寄站內邀請：先出確認框；取消不送
    await cardEls.nth(1).getByRole('button', {name: '寄站內邀請'}).click();
    const dialog = panel.locator('[data-invite-confirm="c"]');
    await dialog.waitFor();
    ok(await dialog.isVisible() && (await dialog.textContent()).includes('青年團隊'), 'clicking 寄站內邀請 shows a confirmation');
    ok((await evs('invite')).length === 0, 'no invite event before confirming');
    await dialog.getByRole('button', {name: '取消'}).click();
    await page.waitForTimeout(200);
    ok(await panel.locator('[data-invite-confirm]').count() === 0 && (await evs('invite')).length === 0, 'cancel closes the dialog and sends nothing');

    // 4. 確定 → invite（confirmed:true）
    await cardEls.nth(1).getByRole('button', {name: '寄站內邀請'}).click();
    await panel.locator('[data-invite-confirm="c"]').getByRole('button', {name: '確定寄出'}).click();
    await waitAction('invite');
    assert.deepEqual(await evs('invite'), [{kind: 'match_task', action: 'invite', task_id: 'task-1', target: 'c', confirmed: true}]);
    ok(true, 'confirming sends one invite event {target, confirmed:true}');

    // 5. 伺服器回寫狀態 → 卡上顯示
    await push({...done, card_state: {b: {favorite: true}, c: {invite: 'sent'}}});
    await panel.locator('[data-match-card="c"] [data-card-state]').getByText('已寄出站內邀請').waitFor();
    ok(await panel.locator('[data-match-card="c"] [data-card-invite]').isDisabled(), 'sent invite cannot be sent again');
    ok((await panel.locator('[data-match-card="b"] [data-card-state]').textContent()).includes('已收藏'), 'favorite state shown');

    // 6. 新任務清掉卡
    await push({...base, task_id: 'task-2', status: 'select', result: null});
    await panel.locator('[data-match-start]').waitFor();
    ok(await panel.locator('[data-match-card]').count() === 0, 'new task clears the cards');

    assert.deepEqual(errors, []);
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
