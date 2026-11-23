// #232 等待不僵住：真實 overlay ＋ embed 頁，模擬後端每 1 秒推一次進度、共 12 秒。
// 桌機與手機（390×844）每 0.5 秒截圖：每個 2 秒區間畫面都要有變化；判斷中星球看得到、顆數隨進度增加；
// 步驟列在第一屏；沒有「更新進度」鈕；建議卡出現後第一張卡在視窗內。最後檢查 30 秒沒新進度的小字。
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
// 與 app/apps/match_analysis/embed_route.py 相同：live-match 才補 match-task.js 與 match-cards.js。
const inject = html => html.replace(/<\/body>(?![\s\S]*<\/body>)/,
  '<script src="./match-task.js?v=live-match"></script><script src="../tangle/match-cards.js?v=live-match"></script></body>');
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

// ── 模擬後端（與 task.py 的 _run／preview 同形）────────────────────────
const KEYS = {B1:'空間與場域',B2:'產品與生產',B3:'服務與體驗',B4:'內容與品牌',B5:'人才與專業',B6:'社群與關係',B7:'市場與通路',B8:'治理與平台'};
const ids = ['p-a', 'p-b', 'p-c', 'p-d', 'p-e'];
const names = {'p-a':'大庄社區','p-b':'農產合作社','p-c':'青年團隊','p-d':'導覽協會','p-e':'漁村工作室'};
const roles = {'p-a': {B2:'need', B4:'offer', B7:'need'}, 'p-b': {B2:'offer', B7:'offer'}, 'p-c': {B4:'need', B6:'offer'},
  'p-d': {B7:'need', B8:'offer'}, 'p-e': {B3:'offer'}};
const side = (pid, lit = true) => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k =>
  [k, {role: lit && roles[pid][k] || 'none', evidence: lit && roles[pid][k] ? [`${names[pid]}：${KEYS[k]}`] : []}]))});
const projects = ids.map(uuid => ({uuid, name: names[uuid]}));
const targets = ids.slice(1);
const result = {demo: false, note: '本次真實判斷（測試資料）', keys: KEYS, a: 'p-a', not_evaluated: [], projects: ids.map(p => side(p)),
  pairs: targets.map(pb => ({pa: 'p-a', pb, pair: ['p-a', pb].sort().join('|'), status: 'EXPLORE', status_text: '可探索',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null}))};
const cards = targets.map((t, i) => ({target: t, rank: i + 1, name: names[t],
  fields: {'為何推薦': `${names[t]}能補上通路`, '互補性': '高', '建議合作': '一起辦市集'}, '原文段落': [], '未評估': {}}));
const base = {task_id: 'task-232', projects, a: 'p-a', targets, min_targets: 2, max_targets: 4, result: null, error: null,
  cards: [], card_state: {}};
// 第 k 秒的快照：1–5 讀取、6–10 判斷、11 比對、12 完成＋建議卡
function at(k) {
  const progress = [], fetched = [], judged = [];
  for (let i = 1; i <= Math.min(k, 11); i++) {
    if (i <= 5) { fetched.push(ids[i - 1]); progress.push({uuid: ids[i - 1], name: names[ids[i - 1]], step: 'fetch'}); }
    else if (i <= 10) { judged.push(ids[i - 6]); progress.push({uuid: ids[i - 6], name: names[ids[i - 6]], step: 'judge'}); }
    else { progress.push({step: 'judged', count: 5}, {step: 'compare', count: 4}); }
  }
  if (k >= 12) return {...base, status: 'done', progress: [...progress, {step: 'cards', count: 4}], result, cards};
  const preview = fetched.length ? {demo: false, preview: true, keys: KEYS, a: 'p-a', pairs: [], total: 5,
    projects: fetched.map(p => ({...side(p, judged.includes(p)), judged: judged.includes(p)}))} : undefined;
  return {...base, status: 'running', progress, ...(preview ? {preview} : {})};
}

let browser;
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const origin = `http://127.0.0.1:${server.address().port}`;
  browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  const open = async (viewport, setup) => {
    const page = await browser.newPage({viewport, deviceScaleFactor: 1});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    if (setup) await setup(page);
    await page.goto(origin);
    await page.evaluate(() => {
      window.events = [];
      window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); });
    });
    const push = (matchTask, update = true) => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn',
      {detail: {name: 'tangle_workspace', args}})), {mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
    const panel = page.frameLocator('#tangle-ws iframe');
    await push({...base, status: 'loading', progress: []}, false);
    await panel.locator('[data-match-task]').waitFor();
    await push({...base, status: 'select', progress: []});
    await panel.locator('[data-match-start]').waitFor();
    return {page, push, panel, errors};
  };

  for (const [label, viewport] of [['desktop', {width: 1440, height: 1000}], ['mobile', {width: 390, height: 844}]]) {
    const {page, push, panel, errors} = await open(viewport);
    const vh = viewport.height;
    const box = async loc => (await loc.count()) ? loc.first().boundingBox() : null;
    const sample = async () => {
      const shot = await page.screenshot();
      const steps = await box(panel.locator('[data-match-steps]:not([hidden])'));
      const stage = await box(panel.locator('[data-match-stage]'));
      const refresh = await panel.locator('button', {hasText: '更新進度'}).count();
      // 雙緩衝換頁的瞬間舊 iframe 會被拿掉；讀到被拆掉的 frame 時重讀目前那張
      let planets = 0, lit = 0;
      for (let tries = 0; tries < 5 && !planets; tries++) {
        const el = await panel.locator('iframe[data-match-galaxy]').elementHandle({timeout: 200}).catch(() => null);
        const f = el && await el.contentFrame().catch(() => null);
        if (f) {
          ({planets, lit} = await f.evaluate(() => ({
            planets: typeof P !== 'undefined' && document.documentElement.dataset.liveMatch ? P.length : 0,
            lit: new Set([...document.querySelectorAll('[data-kv-owner]')].map(g => g.dataset.kvOwner)).size,
          })).catch(() => ({planets: 0, lit: 0})));
        }
        if (!planets) await page.waitForTimeout(50);
      }
      return {shot, steps, stage, refresh, planets, lit};
    };
    const samples = [];
    const t0 = Date.now();
    for (let i = 0; i <= 24; i++) {
      const wait = t0 + i * 500 - Date.now();
      if (wait > 0) await page.waitForTimeout(wait);
      if (i % 2 === 0) await push(at(i / 2));
      samples.push({k: i / 2, ...(await sample())});
    }
    await page.screenshot({path: `/tmp/match-progress-${label}.png`});

    // 1. 每個 2 秒區間畫面都有變化（不僵住）
    const changed = samples.slice(1).map((s, i) => !s.shot.equals(samples[i].shot));
    for (let i = 0; i + 4 <= changed.length; i++) assert.ok(changed.slice(i, i + 4).some(Boolean), `${label}: frozen ${i / 2}s–${i / 2 + 2}s`);
    ok(true, `${label}: the screen changes within every 2-second window (${changed.filter(Boolean).length}/${changed.length} frames differ)`);

    // 2. 判斷中星球看得到，顆數隨進度增加
    const running = samples.filter(s => s.k >= 1.5 && s.k < 12);
    const counts = running.map(s => s.planets);
    ok(counts.every(n => n > 0), `${label}: planets visible while judging (${counts.join(',')})`);
    ok(counts.every((n, i) => !i || n >= counts[i - 1]) && counts[0] < counts.at(-1) && counts.at(-1) === 4,
      `${label}: planet count grows with progress up to A + 3`);
    const lits = running.map(s => s.lit);
    ok(lits.every((n, i) => !i || n >= lits[i - 1]) && lits[0] === 0 && lits.at(-1) === 4, `${label}: planets light up as they are judged (${lits.join(',')})`);

    // 3. 步驟列與星球都在第一屏；沒有「更新進度」鈕
    ok(running.every(s => s.steps && s.steps.y >= 0 && s.steps.y + s.steps.height <= vh), `${label}: step bar is on the first screen`);
    ok(running.every(s => s.stage && Math.min(vh, s.stage.y + s.stage.height) - Math.max(0, s.stage.y) >= 200),
      `${label}: the galaxy is on the first screen (not a dark empty screen)`);
    ok(samples.every(s => s.refresh === 0), `${label}: no 「更新進度」 button`);
    const stepText = await panel.locator('[data-match-steps]').innerText();
    ok(/①.*讀取計畫/.test(stepText) && /④.*寫建議/.test(stepText), `${label}: step bar labels`);

    // 4. 建議卡淡入，第一張卡在視窗內
    const first = panel.locator('[data-match-card]').first();
    await first.waitFor();
    ok(await first.evaluate(el => el.classList.contains('mt-fade')), `${label}: cards fade in`);
    await page.waitForTimeout(1200);
    const card = await first.boundingBox();
    ok(card && card.y >= 0 && card.y < vh - 40, `${label}: first card is scrolled into view (y=${card && Math.round(card.y)})`);
    ok(await panel.locator('[data-match-steps] li[data-state="done"]').count() === 4, `${label}: all four steps checked when done`);
    assert.deepEqual(errors, []);
    await page.close();
  }

  // 5. 30 秒沒新進度 → 小字可點，點了送 get
  {
    const {page, push, panel, errors} = await open({width: 1440, height: 1000}, p => p.clock.install());
    await push(at(3));
    await panel.locator('[data-match-steps] li[data-state="active"]').waitFor();
    ok((await panel.locator('[data-match-steps] li[data-state="active"]').innerText()).includes('3/5'), 'active step shows the count (3/5)');
    await page.clock.runFor(20000);
    await push(at(4));   // 有新進度 → 重新計時
    await page.clock.runFor(20000);
    ok(await panel.locator('[data-match-stale]').count() === 0, 'no stale hint while progress keeps arriving');
    await page.clock.runFor(11000);
    const hint = panel.locator('[data-match-stale]');
    await hint.waitFor();
    ok((await hint.innerText()) === '沒有收到新進度，按這裡重新整理', 'stale hint after 30 s without new progress');
    const gets = await page.evaluate(() => events.filter(e => e.action === 'get').length);
    await hint.click();
    await page.waitForFunction(n => events.filter(e => e.action === 'get').length > n, gets);
    ok(await hint.count() === 0, 'clicking the hint asks the server again and hides the hint');
    assert.deepEqual(errors, []);
    await page.close();
  }

  console.log(`checks ${checks}`);
  console.log('PASS');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close().catch(() => {});
  server.close();
});
