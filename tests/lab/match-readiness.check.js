// #238 媒合準備度瀏覽器契約：選好 A 先看資料夠不夠（四項 ✅／⚠／？）；不夠時提示＋兩個選擇，
// 「先直接媒合」照常開始、「回答幾個問題」一次一題＋問要不要補進計畫理念；資料完整只一行「可以開始」。
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


const ids = ['low-a', 'full-a', 'p-b', 'p-c', 'p-d'];
const names = {'low-a': '資料少的 A', 'full-a': '資料齊的 A', 'p-b': '對象 B', 'p-c': '對象 C', 'p-d': '對象 D'};
const projects = ids.map(uuid => ({uuid, name: names[uuid]}));
const LABEL = {offer: '你能提供什麼', need: '你需要什麼', scale: '規模與時間', collab: '想怎麼合作'};
const STATE = {ok: '足夠', vague: '不夠具體', missing: '還沒寫'};
const ICON = {ok: '✅', vague: '⚠', missing: '？'};
const item = (key, state) => ({key, state, label: LABEL[key], icon: ICON[state], state_text: STATE[state]});
const texts = {hint: '資料不夠也可以直接媒合；補完推薦會更準', complete: '資料完整，可以開始', ask: '回答幾個問題（約 2 分鐘）',
  skip: '先直接媒合', other: '其他（自己寫）', stop: '先停在這', consent: '要不要補進計畫理念（不會改原本寫的）'};
// 與 app/matching/readiness.build 產生的形狀相同
const LOW = {a: 'low-a', state: 'ready', complete: false, texts,
  items: [item('offer', 'ok'), item('need', 'vague'), item('scale', 'missing'), item('collab', 'missing')],
  questions: [
    {key: 'need', text: '你最需要對方幫忙的是哪一種？', options: ['資金或資源', '專業人才', '行銷與通路', '場地']},
    {key: 'scale', text: '這個計畫大概的規模與時間？', options: ['小型試辦（3 個月內）', '一年期計畫', '長期經營（一年以上）']},
    {key: 'collab', text: '你想怎麼跟對方合作？', options: ['共同辦活動', '資源互換', '長期夥伴關係', '一起爭取計畫']},
  ]};
const FULL = {a: 'full-a', state: 'ready', complete: true, texts, questions: [],
  items: ['offer', 'need', 'scale', 'collab'].map(k => item(k, 'ok'))};

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
    const base = {task_id: 'task-r', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null};
    const sel = extra => ({...base, status: 'select', projects, initiable: ['low-a', 'full-a'], ...extra});

    await push({...base, status: 'loading'}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await waitAction('get');

    // 1. 選好 A 的當下就向伺服器要準備度
    await push(sel());
    await panel.locator('[data-match-a]').selectOption('low-a');
    await page.waitForFunction(() => events.some(e => e.action === 'readiness' && e.a === 'low-a'));
    const rq = (await evs('readiness')).find(e => e.a === 'low-a');
    assert.deepEqual(rq, {kind: 'match_task', action: 'readiness', task_id: 'task-r', a: 'low-a'});
    ok(true, 'picking A sends a readiness request for that A');

    // 2. 資料少的 A：四項 + 兩個按鈕 + 提示；開始媒合不被擋
    await push(sel({readiness: LOW}));
    const box = panel.locator('[data-match-readiness]');
    await box.locator('[data-match-ready]').first().waitFor();
    const rows = await box.locator('[data-match-ready]').evaluateAll(ls => ls.map(l => [l.dataset.matchReady, l.dataset.state, l.textContent]));
    ok(rows.map(r => r[0]).join() === 'offer,need,scale,collab', `four readiness items (${rows.map(r => r[0])})`);
    ok(rows.every(([k, st, t]) => t.includes(LABEL[k]) && t.includes(ICON[st]) && t.includes(STATE[st])),
      `each item shows icon + label + state (${rows.map(r => r[2]).join(' / ')})`);
    ok((await box.locator('[data-match-ready-msg]').textContent()).includes('資料不夠也可以直接媒合；補完推薦會更準'), 'hint: missing data never blocks');
    ok((await box.locator('[data-match-ready-ask]').textContent()).includes('回答幾個問題（約 2 分鐘）'), 'button: answer a few questions');
    ok((await box.locator('[data-match-ready-skip]').textContent()).includes('先直接媒合'), 'button: match right away');
    ok(await panel.locator('[data-match-a]').inputValue() === 'low-a', 'A selection kept across the readiness push');

    // 3. 「先直接媒合」→ 勾對象 → 開始
    await box.locator('[data-match-ready-skip]').click();
    ok(await box.locator('[data-match-ready-ask]').count() === 0, 'skip collapses the readiness choices');
    const start = panel.locator('[data-match-start]');
    for (const t of ['p-b', 'p-c']) await panel.locator(`[data-match-target="${t}"]`).check();
    ok(!(await start.isDisabled()), 'start is enabled with 2 targets despite missing data');
    await start.click();
    await waitAction('select');
    assert.deepEqual((await evs('select'))[0], {kind: 'match_task', action: 'select', task_id: 'task-r', a: 'low-a', targets: ['p-b', 'p-c']});
    ok(true, '「先直接媒合」 lets you pick targets and start (select sent)');

    // 4. 「回答幾個問題」：第 1 題 + 選項 → 點選項 → 問要不要補進計畫理念
    await push({...sel({readiness: LOW}), task_id: 'task-r2'});
    await panel.locator('[data-match-a]').selectOption('low-a');
    await box.locator('[data-match-ready-ask]').waitFor();
    await box.locator('[data-match-ready-ask]').click();
    const q = box.locator('[data-match-ready-question]');
    await q.waitFor();
    ok((await q.textContent()) === LOW.questions[0].text, 'question 1 is shown (one at a time)');
    ok((await box.locator('[data-match-ready-step]').textContent()).includes('1'), 'step indicator shows question 1');
    const opts = await box.locator('[data-match-ready-opt]').allTextContents();
    ok(opts.length >= 2 && opts.length <= 4 && opts.join() === LOW.questions[0].options.join(), `2–4 option buttons (${opts})`);
    ok((await box.locator('[data-match-ready-other]').textContent()).includes('其他（自己寫）'), 'option: other (write your own)');
    ok(await box.locator('[data-match-ready-stop]').isVisible(), '「先停在這」 is available');
    ok(await panel.locator('[data-match-start]').count() === 1 && await panel.locator('[data-match-target="p-b"]').isEnabled(),
      'targets and start stay available while answering');
    const answers = (await evs('ready_answer')).length;
    await box.locator('[data-match-ready-opt="1"]').click();
    await box.locator('[data-match-ready-consent]').waitFor();
    ok((await box.locator('[data-match-ready-consent]').textContent()).includes('要不要補進計畫理念'), 'clicking an option asks 要不要補進計畫理念');
    ok((await evs('ready_answer')).length === answers, 'nothing is written before consent');
    // 不同意 → 不寫回，進到第 2 題
    await box.locator('[data-match-ready-no]').click();
    await q.waitFor();
    ok((await q.textContent()) === LOW.questions[1].text, 'declining moves on to question 2');
    ok((await evs('ready_answer')).filter(e => e.consent === true).length === 0, 'declining sends no consented writeback');
    // 同意 → 送出（伺服器才寫回）
    await box.locator('[data-match-ready-opt="0"]').click();
    await box.locator('[data-match-ready-yes]').click();
    await page.waitForFunction(() => events.some(e => e.action === 'ready_answer' && e.consent === true));
    const sent = (await evs('ready_answer')).filter(e => e.consent === true);
    assert.deepEqual(sent[0], {kind: 'match_task', action: 'ready_answer', task_id: 'task-r2', a: 'low-a', key: 'scale',
      answer: LOW.questions[1].options[0], consent: true});
    ok(true, 'consent sends ready_answer with the picked answer');
    ok((await q.textContent()) === LOW.questions[2].text, 'question 3 follows');
    await box.locator('[data-match-ready-stop]').click();
    ok(await box.locator('[data-match-ready-question]').count() === 0, '「先停在這」 ends the questions');
    ok(await panel.locator('[data-match-start]').count() === 1, 'start button still there after stopping');

    // 5. 資料完整的 A：只一行「可以開始」
    await push({...sel({readiness: FULL}), task_id: 'task-r3'});
    await panel.locator('[data-match-a]').selectOption('full-a');
    await box.locator('[data-match-ready-complete]').waitFor();
    const lines = await box.evaluate(b => [...b.children].filter(c => !c.hidden).map(c => c.textContent));
    ok(lines.length === 1 && lines[0].includes('可以開始'), `complete data shows exactly one line (${lines})`);
    ok(await box.locator('[data-match-ready], [data-match-ready-ask], [data-match-ready-skip]').count() === 0,
      'complete data shows no item list or buttons');

    ok(errors.length === 0, `no page errors (${errors.join('; ')})`);
    console.log(`${checks} checks`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
