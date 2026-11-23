// #229 外文通道：媒合工作區「實站」殘留中文。#226 的檢查只收面板（.desk-top＋[data-match-task]），
// 這支改收「整個真實頁面」：真實 overlay（public/tangle-lab-overlay.js）＋ 真實 embed.html?mode=match&v=live-match
// （照 app/apps/match_analysis/embed_route.py 補上 match-task.js、match-cards.js；yunlin.js 等原本就載入的都照載）。
// lang＝en／ja／ko 各走「載入 → 選案 → 判斷中 → 判斷完成 → 建議卡」，每一步收集：
//   外框（#tangle-ws）可見文字與 aria-label／title／placeholder（含 iframe 的 title），
//   iframe 內整個 body 的可見文字與可見元素的 aria-label／title／placeholder；
// 扣掉假資料中的專案名稱與原文引用後：en／ko 不得有漢字；ja 不得有中文專用字形、也不得有「長句無假名」。
// lang 來源：en、ja 由任務狀態帶 lang（en 同時放一個 ja cookie，確認任務狀態優先）；ko 只靠 eva_lang cookie。
// lang＝zh（不帶 lang、無 cookie）時外框文字、面板文字（.desk-top＋[data-match-task]）與改動前（beta a69d75e）相同。
// 另確認法規模式（mode=law）的外框維持中文。
// 自己伺服 repo；Playwright 由 NODE_PATH 提供（找不到時退回 /tmp/pw/node_modules）。最後一行 PASS。
// `--dump` 印出 zh 各步文字（產生下方 ZH_BASELINE 用）。
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
// 與 embed_route.py 相同：只有 mode=match&v=live-match 才補 match-task.js 與 match-cards.js。
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
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript; charset=utf-8' : file.endsWith('.html') ? 'text/html; charset=utf-8'
      : file.endsWith('.css') ? 'text/css' : file.endsWith('.json') ? 'application/json' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});

// ── 假資料：專案名稱、計畫原文是使用者資料（不翻）；LLM 寫的卡片欄位依語言給。
const names = {a: '大庄社區', b: '農產合作社', c: '青年團隊', d: '導覽協會'};
const QA = '需要行銷通路協助販售農產品', QB = '有通路可以協助販售';
const DATA = [...Object.values(names), QA, QB];
const targets = ['b', 'c', 'd'];
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const KEYS = {B1: '空間與場域', B5: '人才與專業', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const STATUS = {b: ['EXPLORE', '可探索'], c: ['CLARIFY_FIRST', '先補資料'], d: ['ELIGIBLE', '可排序・未建議']};
const result = {
  demo: false, keys: KEYS, a: 'a', not_evaluated: [],
  note: 'B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。',
  projects: ['a', ...targets].map(side),
  pairs: targets.map((pb, i) => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: STATUS[pb][0], status_text: STATUS[pb][1],
    relations: {}, counts: {complement: 1, third: i, peer: 0}, next_question: null})),
};
const FIELD_TEXT = {
  zh: ['符合規則「一方需要、另一方能提供」。', '一方有場地、一方有通路。', '雙方都能得到實際幫助。', '先辦一場小型市集。', '市集預計在哪個月份？', '不足'],
  en: ['Matches the rule "one side needs, the other can provide".', 'One has a venue, the other has sales channels.',
    'Both sides get practical help.', 'Start with a small market.', 'Which month is the market planned for?', 'Schedules may not align.'],
  ja: ['「一方が必要とし、もう一方が提供できる」というルールに合っています。', '一方には場所があり、もう一方には販路があります。',
    '双方が実際に助けを得られます。', 'まず小さなマーケットを開きましょう。', 'マーケットは何月の予定ですか？', 'スケジュールが合わないかもしれません。'],
  ko: ['"한쪽이 필요로 하고 다른 쪽이 제공할 수 있다"는 규칙에 맞습니다.', '한쪽은 장소가, 다른 쪽은 판로가 있습니다.',
    '양쪽 모두 실질적인 도움을 받습니다.', '먼저 작은 장터를 열어 보세요.', '장터는 몇 월로 예정되어 있나요?', '일정이 맞지 않을 수 있습니다.'],
};
const FIELD_KEYS = ['為何推薦', '互補性', '互惠價值', '建議合作', '待確認', '風險'];
const NE = {'議題與目標對象': '未評估', '合作可執行性': '未評估', '跨國語境與成本': '未評估', '階段與時程': '未評估'};
const cardsFor = lang => targets.map((target, i) => ({
  rank: i + 1, target, name: names[target],
  fields: Object.fromEntries(FIELD_KEYS.map((k, j) => [k, FIELD_TEXT[lang][j]])),
  '未評估': NE,
  '原文段落': [{'計畫': names.a, '段落': 1, '原文': QA}, {'計畫': names[target], '段落': 2, '原文': QB}],
  '合作起步草案': null,
}));

const HAN = /[\u3400-\u9fff\uf900-\ufaff]/; // 中日韓漢字（含相容區）；不含諺文
const KANA = /[\u3040-\u30ff]/;
const CN_ONLY = /[們這會為與對說號關讀從還經實寫錄邀狀專畫處應來嗎您讓麼將个们这会为与对说号关读从还经实写录邀状专画处应来吗让么将选择项确认补资时间开启请]/;
const strip = s => DATA.reduce((t, d) => t.split(d).join(''), s);
function violations(lang, texts) {
  const bad = [];
  for (const raw of texts) {
    const t = strip(raw);
    if (lang === 'ja') {
      if (CN_ONLY.test(t)) bad.push(`中文字形: ${raw}`);
      for (const piece of t.split(/[\n。！？!?]/)) {
        const han = (piece.match(new RegExp(HAN.source, 'g')) || []).length;
        if (han >= 4 && piece.trim().length >= 8 && !KANA.test(piece)) bad.push(`長句無假名: ${piece.trim()}`);
      }
    } else if (HAN.test(t)) bad.push(`漢字: ${raw}`);
  }
  return bad;
}

// 頁面裡收集可見文字：root 的 innerText（不含 display:none／hidden）＋ 可見元素的 aria-label／title／placeholder。
function collectIn(rootSel) {
  const out = [];
  const roots = rootSel ? [...document.querySelectorAll(rootSel)] : [document.body];
  const visible = el => {
    if (el.closest('[hidden]')) return false;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return false;
    return el.getClientRects().length > 0 || cs.position === 'fixed';
  };
  for (const r of roots) {
    if (!r) continue;
    out.push(...(r.innerText || '').split('\n').map(s => s.trim()).filter(Boolean));
    for (const el of [r, ...r.querySelectorAll('*')]) {
      if (!visible(el)) continue;
      for (const at of ['aria-label', 'title', 'placeholder']) if (el.getAttribute(at)) out.push(`[${at}] ${el.getAttribute(at)}`);
    }
  }
  return out;
}
// #226 的面板範圍（zh 比對用）。
function collectPanel() {
  const out = [];
  const desk = document.querySelector('.desk');
  if (desk?.getAttribute('aria-label')) out.push(`[aria-label] ${desk.getAttribute('aria-label')}`);
  const roots = [document.querySelector('.desk-top'), document.querySelector('[data-match-task]'),
    ...document.querySelectorAll('.mc-dialog')].filter(Boolean);
  for (const r of roots) {
    out.push(...r.innerText.split('\n').map(s => s.trim()).filter(Boolean));
    for (const el of [r, ...r.querySelectorAll('*')]) {
      if (el.closest('[hidden]') || (el.offsetParent === null && el !== r && getComputedStyle(el).position !== 'fixed')) continue;
      for (const at of ['aria-label', 'title', 'placeholder']) if (el.getAttribute(at)) out.push(`[${at}] ${el.getAttribute(at)}`);
    }
  }
  return out;
}

async function walk(browser, port, lang, {snapshotLang, cookie}) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}});
  if (cookie) await ctx.addCookies([{name: 'eva_lang', value: cookie, url: `http://127.0.0.1:${port}`}]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${port}`);
  await page.evaluate(() => {
    window.events = [];
    window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); });
  });
  const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
  const withLang = t => snapshotLang ? {...t, lang: snapshotLang} : t;
  const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask: withLang(matchTask), ...(update ? {update: true} : {})});
  const waitAction = action => page.waitForFunction(a => events.some(e => e.action === a), action);
  const panel = page.frameLocator('#tangle-ws iframe');
  const frame = () => page.frames().find(f => /embed\.html\?.*mode=match/.test(f.url()));
  const steps = {}, panels = {};
  const collect = async step => {
    await page.waitForTimeout(200);
    const outer = await page.evaluate(collectIn, '#tangle-ws');
    const inner = await frame().evaluate(collectIn, null);
    steps[step] = [...outer.map(s => `outer: ${s}`), ...inner];
    panels[step] = [...outer.map(s => `outer: ${s}`), ...await frame().evaluate(collectPanel)];
  };
  const base = {task_id: 'task-1', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null,
    cards: [], card_state: {}};
  try {
    await push({...base, status: 'loading'}, false);
    await panel.locator('[data-match-task]').waitFor();
    await waitAction('get');
    await push({...base, status: 'loading'});
    await page.waitForFunction(() => !document.getElementById('tangle-ws').classList.contains('hide'));
    await collect('loading');
    await push({...base, status: 'select', projects, initiable: ['a', 'b']});
    await panel.locator('[data-match-start]').waitFor();
    await panel.locator('[data-match-a]').selectOption('a');
    for (const t of targets) await panel.locator(`[data-match-target="${t}"]`).check();
    await collect('select');
    await panel.locator('[data-match-start]').click();
    await waitAction('select');
    await push({...base, status: 'running', projects, a: 'a', targets, progress: [{uuid: 'a', name: names.a, step: 'fetch'}]});
    await panel.locator('[data-match-steps] li').first().waitFor();  // #232 判斷中不再有「更新進度」按鈕，改等步驟條
    await collect('running');
    const done = {...base, status: 'done', projects, a: 'a', targets, result, cards: cardsFor(lang)};
    await push(done);
    await panel.locator('[data-match-cards] [data-match-card]').first().waitFor();
    await panel.locator('iframe[data-match-galaxy]').waitFor();
    await collect('done');
    // 星圖頁（巢狀 iframe）裡的可見文字與提示，例如「重設」。
    const gal = () => page.frames().find(f => /tangle-match\.html\?liveMatch=1/.test(f.url()));
    for (let i = 0; i < 50 && !(gal() && await gal().evaluate(() => !!document.getElementById('zFit')).catch(() => false)); i++) await page.waitForTimeout(100);
    assert.ok(gal(), `${lang}: galaxy frame loaded`);
    await page.waitForTimeout(300);
    steps.done.push(...(await gal().evaluate(collectIn, null)).map(t => `galaxy: ${t}`));
    assert.deepEqual(errors, [], `${lang}: page errors`);
    return {steps, panels};
  } finally { await ctx.close(); }
}

// 法規模式的外框（不帶 lang、無 cookie）：維持中文。
async function lawOuter(browser, port, cookie) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}});
  if (cookie) await ctx.addCookies([{name: 'eva_lang', value: cookie, url: `http://127.0.0.1:${port}`}]);
  const page = await ctx.newPage();
  try {
    await page.goto(`http://127.0.0.1:${port}`);
    await page.evaluate(() => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args: {mode: 'law', v: '1'}}})));
    await page.locator('#tangle-ws-close').waitFor();
    return await page.evaluate(collectIn, '#tangle-ws');
  } finally { await ctx.close(); }
}

// lang＝zh 時外框＋面板文字（改動前 beta a69d75e 以 --dump 取得）。
// #232：移除「更新進度」、加入步驟條後以 --dump 重新產生（差異僅此兩項，2026-11-23 PM 核對）。
const ZH_BASELINE = {
 "loading": [
  "outer: 收合 ↙",
  "outer: [title] 收合工作區，回到原本的聊天畫面",
  "outer: [title] 雲林專案工作區",
  "[aria-label] 策略工作區",
  "專案媒合工作區",
  "載入專案清單中…"
 ],
 "select": [
  "outer: 收合 ↙",
  "outer: [title] 收合工作區，回到原本的聊天畫面",
  "outer: [title] 雲林專案工作區",
  "[aria-label] 策略工作區",
  "專案媒合工作區",
  "請選擇 A，以及 2–4 個要比較的對象。",
  "專案 A",
  "大庄社區",
  "農產合作社",
  "比較對象（2–4 個）",
  "大庄社區",
  "農產合作社",
  "青年團隊",
  "導覽協會",
  "開始媒合 →已選 3 個",
  "[aria-label] 專案 A"
 ],
 "running": [
  "outer: 收合 ↙",
  "outer: [title] 收合工作區，回到原本的聊天畫面",
  "outer: [title] 雲林專案工作區",
  "[aria-label] 策略工作區",
  "專案媒合 / 大庄社區",
  "正在判斷各案的需要／能提供…",
  "① 讀取計畫（1/4）",
  "② 判斷需要與能提供（0/4）",
  "③ 比對互補",
  "④ 寫建議",
  "已讀取：大庄社區"
 ],
 "done": [
  "outer: 收合 ↙",
  "outer: [title] 收合工作區，回到原本的聊天畫面",
  "outer: [title] 雲林專案工作區",
  "[aria-label] 策略工作區",
  "專案媒合 / 大庄社區",
  "媒合判斷完成（不推薦、不自動聯絡）",
  "① 讀取計畫",
  "② 判斷需要與能提供",
  "③ 比對互補",
  "④ 寫建議",
  "開始新媒合",
  "3 案比較（A：大庄社區）",
  "對象\t狀態\t互補候選\t共同尋找第三方\t可聯合或交流\t畫面",
  "農產合作社\t可探索\t1\t0\t0\t放進星圖 請 Eva 說明",
  "青年團隊\t先補資料\t1\t1\t0\t放進星圖 請 Eva 說明",
  "導覽協會\t可排序・未建議\t1\t2\t0\t放進星圖 請 Eva 說明",
  "B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。",
  "媒合建議卡",
  "依這次判斷排出的建議；要不要聯絡、怎麼開始由你決定。寄站內邀請前會再請你確認。",
  "1. 農產合作社",
  "為何推薦",
  "符合規則「一方需要、另一方能提供」。",
  "原文",
  "大庄社區・第 1 段：「需要行銷通路協助販售農產品」",
  "農產合作社・第 2 段：「有通路可以協助販售」",
  "互補性",
  "一方有場地、一方有通路。",
  "互惠價值",
  "雙方都能得到實際幫助。",
  "建議合作",
  "先辦一場小型市集。",
  "待確認",
  "市集預計在哪個月份？",
  "風險",
  "不足",
  "未評估",
  "議題與目標對象：未評估、合作可執行性：未評估、跨國語境與成本：未評估、階段與時程：未評估",
  "收藏",
  "略過",
  "補資料",
  "寄站內邀請",
  "2. 青年團隊",
  "為何推薦",
  "符合規則「一方需要、另一方能提供」。",
  "原文",
  "大庄社區・第 1 段：「需要行銷通路協助販售農產品」",
  "青年團隊・第 2 段：「有通路可以協助販售」",
  "互補性",
  "一方有場地、一方有通路。",
  "互惠價值",
  "雙方都能得到實際幫助。",
  "建議合作",
  "先辦一場小型市集。",
  "待確認",
  "市集預計在哪個月份？",
  "風險",
  "不足",
  "未評估",
  "議題與目標對象：未評估、合作可執行性：未評估、跨國語境與成本：未評估、階段與時程：未評估",
  "收藏",
  "略過",
  "補資料",
  "寄站內邀請",
  "3. 導覽協會",
  "為何推薦",
  "符合規則「一方需要、另一方能提供」。",
  "原文",
  "大庄社區・第 1 段：「需要行銷通路協助販售農產品」",
  "導覽協會・第 2 段：「有通路可以協助販售」",
  "互補性",
  "一方有場地、一方有通路。",
  "互惠價值",
  "雙方都能得到實際幫助。",
  "建議合作",
  "先辦一場小型市集。",
  "待確認",
  "市集預計在哪個月份？",
  "風險",
  "不足",
  "未評估",
  "議題與目標對象：未評估、合作可執行性：未評估、跨國語境與成本：未評估、階段與時程：未評估",
  "收藏",
  "略過",
  "補資料",
  "寄站內邀請",
  "[title] 本次媒合星系"
 ]
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    const zh = await walk(browser, port, 'zh', {});
    if (process.argv.includes('--dump')) { console.log(JSON.stringify(zh.panels, null, 1)); return; }
    if (process.argv.includes('--dump-all')) { console.log(JSON.stringify(zh.steps, null, 1)); return; }
    assert.ok(ZH_BASELINE, 'ZH_BASELINE missing');
    for (const step of Object.keys(ZH_BASELINE)) assert.deepEqual(zh.panels[step], ZH_BASELINE[step], `zh step ${step} unchanged`);
    ok(Object.keys(zh.panels).join() === Object.keys(ZH_BASELINE).join(), 'lang=zh: frame and panel show exactly the current text');
    ok(zh.steps.done.includes('galaxy: [title] 重設'), 'lang=zh: galaxy reset tip unchanged');

    const runs = [['en', {snapshotLang: 'en', cookie: 'ja'}], ['ja', {snapshotLang: 'ja', cookie: 'ja'}], ['ko', {cookie: 'ko'}]];
    for (const [lang, how] of runs) {
      const {steps} = await walk(browser, port, lang, how);
      if (process.argv.includes('--show')) console.log(lang, JSON.stringify(steps, null, 1));
      for (const [step, texts] of Object.entries(steps)) {
        assert.ok(texts.some(t => t.startsWith('outer: ')), `${lang} ${step}: collected frame text`);
        assert.ok(texts.length > 5, `${lang} ${step}: collected page text`);
        const bad = violations(lang, texts);
        assert.deepEqual(bad, [], `${lang} ${step}: ${bad.join(' | ')}`);
      }
      assert.ok(steps.done.some(t => t.startsWith('galaxy: [title] ')), `${lang}: collected galaxy text`);
      const all = Object.values(steps).flat().join('\n');
      assert.ok(all.includes(names.a) && all.includes(QA), `${lang}: project names and quotes are kept as-is`);
      ok(true, `lang=${lang} (${how.snapshotLang ? 'task state' : 'cookie'}): real overlay + embed.html, ${Object.keys(steps).join(' → ')} has no Chinese text`);
    }

    const law = await lawOuter(browser, port, null);
    assert.deepEqual(law, ZH_BASELINE.loading.filter(t => t.startsWith('outer: ')).map(t => t.slice(7)), 'law frame unchanged');
    ok(true, 'law mode (no lang): frame text unchanged');
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
