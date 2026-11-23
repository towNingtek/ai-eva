// #242 媒合準備度在深色工作區上的對比：真實 overlay＋embed.html?mode=match，推入含 ok／vague／missing 三種狀態的
// 準備度並打開第 1 題，等動畫結束後逐元素算「前景色 vs 實際祖先背景色（含半透明疊色）」：
// 準備度區塊內所有可見文字 ≥ 4.5:1；工作區內 .mt-note 文字 ≥ 4.5:1；三種狀態仍以顏色＋圖示區分。最後一行 PASS。
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
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html'
      : file.endsWith('.css') ? 'text/css' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});

const ids = ['low-a', 'p-b', 'p-c'];
const projects = ids.map(uuid => ({uuid, name: uuid}));
const LABEL = {offer: '你能提供什麼', need: '你需要什麼', scale: '規模與時間', collab: '想怎麼合作'};
const STATE = {ok: '足夠', vague: '不夠具體', missing: '還沒寫'};
const ICON = {ok: '✅', vague: '⚠', missing: '？'};
const item = (key, state) => ({key, state, label: LABEL[key], icon: ICON[state], state_text: STATE[state]});
const LOW = {a: 'low-a', state: 'ready', complete: false, texts: {},
  items: [item('offer', 'ok'), item('need', 'vague'), item('scale', 'missing'), item('collab', 'missing')],
  questions: [
    {key: 'need', text: '你最需要對方幫忙的是哪一種？', options: ['資金或資源', '專業人才', '行銷與通路', '場地']},
    {key: 'scale', text: '這個計畫大概的規模與時間？', options: ['小型試辦（3 個月內）', '一年期計畫']},
  ]};

// 在頁面內執行：逐元素算前景色與實際祖先背景（由下往上疊合半透明背景、乘上 opacity 的前景）
function measure(selector) {
  const parse = c => {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
  };
  const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a),
    b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lum = c => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (x, y) => { const [a, b] = [lum(x), lum(y)].sort((p, q) => q - p); return (a + 0.05) / (b + 0.05); };
  const bgOf = el => {
    const chain = [];
    for (let e = el; e; e = e.parentElement) chain.push(e);
    // 背景色由下往上疊；漸層（如 .desk 的 radial-gradient）每個色標都當成可能的實際背景，取最壞者
    let bgs = [{r: 255, g: 255, b: 255, a: 1}];   // 畫布底
    const images = [];
    for (const e of chain.reverse()) {
      const cs = getComputedStyle(e);
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) bgs = bgs.map(b => over(c, b));
      if (cs.backgroundImage && cs.backgroundImage !== 'none') {
        images.push(e.tagName + '.' + e.className);
        const stops = (cs.backgroundImage.match(/rgba?\([^)]+\)/g) || []).map(parse);
        bgs = bgs.concat(...stops.map(st => bgs.map(b => over(st, b))));
      }
    }
    return {bgs, images};
  };
  const out = [];
  for (const el of document.querySelectorAll(selector)) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())
      || (el.matches('input,button') && (el.value || el.textContent).trim());
    if (!own) continue;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[hidden]')) continue;
    const {bgs, images} = bgOf(el);
    const fg = parse(cs.color);
    const scored = bgs.map(b => [ratio(over(fg, b), b), b]).sort((x, y) => x[0] - y[0]);
    const [worst, bg] = scored[0];
    out.push({tag: el.tagName, cls: el.className, attrs: [...el.attributes].map(a => a.name).filter(n => n.startsWith('data-')).join(' '),
      text: (el.textContent || el.value).trim().slice(0, 30), color: cs.color, bg: `rgb(${bg.r | 0},${bg.g | 0},${bg.b | 0})`,
      images, ratio: Math.floor(worst * 100) / 100});
  }
  return out;
}

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
    const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
    const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
    const base = {task_id: 'task-c', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null};
    await push({...base, status: 'loading'}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await push({...base, status: 'select', projects, initiable: ['low-a'], readiness: LOW, listing: true});
    await panel.locator('[data-match-a]').selectOption('low-a');
    const box = panel.locator('[data-match-readiness]');
    await box.locator('[data-match-ready-ask]').click();
    await box.locator('[data-match-ready-question]').waitFor();
    const frame = page.frames().find(f => f.url().includes('embed.html'));
    ok(!!frame, 'workspace iframe found');
    // 等動畫（淡入等有限動畫）結束；無限的呼吸動畫不影響文字色
    await frame.evaluate(() => Promise.all(document.getAnimations()
      .filter(a => a.effect?.getComputedTiming().endTime !== Infinity).map(a => a.finished.catch(() => {}))));
    await page.waitForTimeout(400);

    // 1. 三種狀態：顏色＋圖示都不同
    const states = await box.locator('[data-match-ready]').evaluateAll(ls => ls.map(l => [l.dataset.state, getComputedStyle(l).color, l.textContent]));
    const byState = Object.fromEntries(states.map(([s, c, t]) => [s, [c, t]]));
    ok(['ok', 'vague', 'missing'].every(s => byState[s] && byState[s][1].includes(ICON[s])), `each state keeps its icon (${states.map(s => s[2])})`);
    ok(new Set(['ok', 'vague', 'missing'].map(s => byState[s][0])).size === 3, `three states use three colors (${states.map(s => s[1])})`);

    // 2. 準備度區塊所有可見文字 ≥ 4.5:1（四項、說明、步驟、問題、選項按鈕）
    const ready = await frame.evaluate(measure, '[data-match-readiness], [data-match-readiness] *');
    for (const r of ready) console.log('  ready', r.ratio, r.color, 'on', r.bg, r.tag, r.attrs || r.cls, r.text, r.images.length ? r.images : '');
    const need = ['data-match-ready-msg', 'data-match-ready-step', 'data-match-ready-question', 'data-match-ready-opt', 'data-match-ready-other', 'data-match-ready-stop'];
    ok(need.every(n => ready.some(r => r.attrs.split(' ').includes(n))), 'measured hint, step, question, options, other and stop');
    ok(ready.filter(r => r.attrs.includes('data-match-ready ') || r.attrs === 'data-match-ready data-state' || r.attrs.startsWith('data-match-ready data-state')).length === 4, 'measured all four items');
    const lowReady = ready.filter(r => r.ratio < 4.5);
    ok(lowReady.length === 0, `readiness text contrast ≥ 4.5:1 (min ${Math.min(...ready.map(r => r.ratio))}; low: ${JSON.stringify(lowReady)})`);

    // 3. 工作區其他 .mt-note ≥ 4.5:1
    const notes = await frame.evaluate(measure, '.mt-note');
    for (const r of notes) console.log('  note', r.ratio, r.color, 'on', r.bg, r.attrs || r.cls, r.text);
    ok(notes.length >= 2, `measured ${notes.length} .mt-note elements`);
    const lowNotes = notes.filter(r => r.ratio < 4.5);
    ok(lowNotes.length === 0, `.mt-note contrast ≥ 4.5:1 (low: ${JSON.stringify(lowNotes)})`);

    ok(errors.length === 0, `no page errors (${errors.join('; ')})`);
    console.log(`${checks} checks`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
