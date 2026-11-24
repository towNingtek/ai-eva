// #250 建議卡「看依據 → 規則說明」不得把原文段落標記（app/i18n/quote.py 的 HTML 註解 quote:original／quote:translation）當字露出。
// 真實 overlay（public/tangle-lab-overlay.js）＋ 真實 embed.html?mode=match&v=live-match（照 embed_route.py 補上
// match-task.js、match-cards.js），推一張「為何推薦」（規則說明）與其他欄位都帶原文／翻譯標記的卡（lang＝en、ja、ko、zh 各一次），
// 展開「看依據」後檢查：
// (a) 卡片可見文字（innerText）與 DOM 文字節點都不含 HTML 註解開頭、quote:original、quote:translation
// (b) 原文片段以帶 data-quote 的元素呈現（規則說明、第一層結論、其他欄位都算）；翻譯段以 data-quote="translation" 呈現
// (c) 原文（中文）照列不翻
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

// 與 app/i18n/quote.py／app/matching/i18n.py quote() 相同的標記
const O = '<!--quote:original-->', OC = '<!--/quote:original-->';
const TR = '<!--quote:translation-->', TRC = '<!--/quote:translation-->';
const ORIG = '帶領遊客體驗竹編課程';
const ORIG2 = '社區活動中心可以借用';
const TRANS = {en: 'Leads visitors through bamboo weaving classes', ja: '観光客に竹編み講座を体験してもらう', ko: '관광객에게 대나무 공예 수업 체험 제공', zh: ''};
const LABEL = {en: '翻譯 Translation', ja: '翻譯 翻訳', ko: '翻譯 번역', zh: '翻譯'};
const RULE = {en: 'rule text', ja: 'ルールの原文', ko: '규칙 원문', zh: '規則原文'};
const q = (lang, text, tr) => `${O}「${text}」${OC}` + (tr ? `${TR}（${LABEL[lang]}：${tr}）${TRC}` : '');

const names = {a: '竹山社區', b: '【媒合測試B】竹山竹藝體驗工坊', c: '農產合作社'};
const targets = ['b', 'c'];
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const KEYS = {B1: '空間與場域', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const result = {
  demo: false, note: 'test', keys: KEYS, a: 'a', not_evaluated: [],
  projects: ['a', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: 'EXPLORE', status_text: '可探索',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null})),
};
const cardFor = lang => {
  const tr = TRANS[lang];
  const why = `Rule "Two-way complement first" (${RULE[lang]}: both sides can meet a need of the other). ` +
    `Services & Experiences: ${names.b} original ${q(lang, ORIG, tr)}, ${names.a} original ${q(lang, ORIG2, tr)}. ` +
    'Ranked #1 by rule "Two-way complement first".';
  return {
    rank: 1, target: 'b', name: names.b,
    fields: {
      '為何推薦': why,
      // 第一層結論來源：第一句就帶原文標記（且長到要截斷）
      '互補性': `${names.b} offers ${q(lang, ORIG, tr)} which ${names.a} needs for its visitor programme and long weekend events.`,
      '互惠價值': `Mutual: ${q(lang, ORIG2, tr)}`,
      '建議合作': 'Start with one pilot workshop.',
      '待確認': `Is ${q(lang, ORIG2, tr)} still true?`, '風險': 'Limited staff.',
    },
    '未評估': {},
    '原文段落': [{'計畫': names.b, '段落': 1, '原文': ORIG}],
    '合作起步草案': null,
  };
};
const other = {
  rank: 2, target: 'c', name: names.c,
  fields: {'為何推薦': 'Good fit.', '互補性': 'Market access.', '互惠價值': '不足', '建議合作': '不足', '待確認': '不足', '風險': '不足'},
  '未評估': {}, '原文段落': [], '合作起步草案': null,
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    for (const lang of ['en', 'ja', 'ko', 'zh']) {
      const page = await browser.newPage({viewport: {width: 1440, height: 900}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:${server.address().port}`);
      const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
      const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
      const base = {task_id: `task-${lang}`, lang, projects, a: 'a', targets, min_targets: 2, max_targets: 4, progress: [], error: null,
                    cards: [], card_state: {}};
      await push({...base, status: 'loading', result: null}, false);
      const panel = page.frameLocator('#tangle-ws iframe');
      await panel.locator('[data-match-task]').waitFor();
      await push({...base, status: 'done', result, cards: [cardFor(lang), other]});
      const card = panel.locator('[data-match-card="b"]');
      await card.waitFor();
      await card.locator('[data-why-toggle]').click();
      await page.waitForTimeout(100);
      const view = await card.evaluate(el => {
        el.querySelector('[data-why-rule]')?.scrollIntoView({block: 'center'});
        const texts = [];
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_COMMENT);
        let comments = 0;
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          if (n.nodeType === 8) comments++; else texts.push(n.textContent);
        }
        const rule = el.querySelector('[data-why-rule] [data-field="為何推薦"]');
        const pick = sel => [...el.querySelectorAll(sel)].map(e => ({kind: e.getAttribute('data-quote'), text: e.textContent}));
        return {
          expanded: el.querySelector('[data-why-toggle]').getAttribute('aria-expanded'),
          inner: el.innerText, texts: texts.join('\n'), comments,
          ruleShown: !!rule && rule.getBoundingClientRect().height > 0,
          ruleQuotes: rule ? pick.call(null, '[data-why-rule] [data-quote]') : [],
          conclusionQuotes: pick('[data-why-conclusion] [data-quote]'),
          fieldQuotes: pick('dd [data-quote]'),
          ruleText: rule?.textContent || '',
        };
      });
      const BAD = ['<!--', 'quote:original', 'quote:translation', '', '', '', ''];
      ok(view.expanded === 'true' && view.ruleShown, `[${lang}] 「看依據」 expanded, 規則說明 visible`);
      ok(BAD.every(b => !view.inner.includes(b)), `[${lang}] (a) visible card text has no marker`);
      ok(BAD.every(b => !view.texts.includes(b)) && view.comments === 0, `[${lang}] (a) DOM text nodes have no marker`);
      const origs = view.ruleQuotes.filter(x => x.kind === 'original').map(x => x.text);
      ok(origs.length === 2 && origs.some(t => t.includes(ORIG)) && origs.some(t => t.includes(ORIG2)),
        `[${lang}] (b) 規則說明 originals rendered as [data-quote] elements: ${JSON.stringify(origs)}`);
      const trs = view.ruleQuotes.filter(x => x.kind === 'translation').map(x => x.text);
      ok(lang === 'zh' ? trs.length === 0 : trs.length === 2 && trs.every(t => t.includes(TRANS[lang]) && t.includes('翻譯')),
        `[${lang}] (b) translations rendered as [data-quote="translation"]: ${JSON.stringify(trs)}`);
      ok(view.conclusionQuotes.some(x => x.kind === 'original' && ORIG.startsWith(x.text.replace(/^「|」$/g, '').replace(/…$/, '')) || x.text.includes(ORIG)),
        `[${lang}] (b) 為何推薦 conclusion: original quote as [data-quote]: ${JSON.stringify(view.conclusionQuotes)}`);
      ok(view.fieldQuotes.filter(x => x.kind === 'original' && x.text.includes(ORIG2)).length === 2,
        `[${lang}] (b) other fields: originals as [data-quote]`);
      ok(view.ruleText.includes(`「${ORIG}」`) && view.ruleText.includes(names.b), `[${lang}] (c) Chinese original kept verbatim`);
      assert.deepEqual(errors, []);
      await page.close();
    }
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
