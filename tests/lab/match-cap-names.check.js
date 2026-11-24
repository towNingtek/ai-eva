// #254 建議卡結論句截斷時不切開專案名稱。
// 真實 overlay（public/tangle-lab-overlay.js）＋ 真實 embed.html?mode=match&v=live-match（補上 match-task.js、match-cards.js），
// lang＝ko／ja／en／zh 各推一次結果：
// (a) 卡 b 的結論來源（互補性第一句）超過 60 字，且第 60 字落在 A 的名稱「[測試] 溪畔社區食農教育」中間 →
//     結論句不含該名稱的任何殘缺前綴（只有完整名稱或完全不出現），以「…」結尾、≤ 60 字。
// (b) 卡 c 的名稱很長（> 60 字）且在句首 → 結論句保留完整名稱，在名稱之後才截斷（以「…」結尾）。
// Playwright 由 NODE_PATH 提供（找不到時退回 /tmp/pw/node_modules）。最後一行 PASS。
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

const NAME = '[測試] 溪畔社區食農教育';
const LONG_NAME = '[測試] 溪畔社區食農教育與青年返鄉共學實驗計畫第二期跨縣市聯合推廣暨在地農產品牌化與通路串接示範工作坊系列活動之社區食農體驗營隊';
assert.ok(Array.from(LONG_NAME).length > 60, 'LONG_NAME must exceed the 60-char cap');
const names = {a: NAME, b: '農產合作社', c: LONG_NAME};
const targets = ['b', 'c'];
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const KEYS = {B1: '空間與場域', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const result = {
  demo: false, keys: KEYS, a: 'a', not_evaluated: [],
  projects: ['a', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: 'EXPLORE', status_text: '-',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null})),
};
// 句子前段（不含句末標點），截到剛好 START 個字，接著放名稱 → 第 60 字（index 59）落在名稱中間。
const START = 52;
const LEAD = {
  ko: '상대 단체는 시장과 유통 경로를 제공할 수 있고 공간과 장소가 필요한 상태이고 지역 주민과 함께 협력하는 기반도 갖춘 상태이고, ',
  ja: '相手側は市場と流通の経路を提供でき、空間と場所を必要としている状態で、地域の住民と一緒に協力する基盤も整っている状態で、さらに、',
  en: 'They can offer market channels and need venues, ',
  zh: '對方能提供市場與通路，也需要空間與場域，雙方在地方上都有長期經營的基礎，彼此的人力與資源可以互相補位，而且都有意願先從小規模的活動開始嘗試，',
};
const TAIL = {ko: ' 과 함께 시장을 열 수 있습니다.', ja: ' と一緒に市場を開けます。', en: ' could run a market together.', zh: ' 可以一起辦市集。'};
const lead = lang => {
  let s = LEAD[lang];
  while (Array.from(s).length < START) s += s;
  return Array.from(s).slice(0, START).join('');
};
const cardsFor = lang => [
  {rank: 1, target: 'b', name: names.b,
   fields: {'為何推薦': '不足', '互補性': lead(lang) + NAME + TAIL[lang], '互惠價值': '不足', '建議合作': '不足', '待確認': '不足', '風險': '不足'},
   '未評估': {}, '原文段落': [], '合作起步草案': null},
  {rank: 2, target: 'c', name: names.c,
   fields: {'為何推薦': '不足', '互補性': LONG_NAME + TAIL[lang], '互惠價值': '不足', '建議合作': '不足', '待確認': '不足', '風險': '不足'},
   '未評估': {}, '原文段落': [], '合作起步草案': null},
];

// 結論句裡出現的名稱前綴都必須是完整名稱；「…」前面不得是名稱的殘缺前綴。
function brokenName(text, name) {
  const body = text.replace(/…$/, '');
  const n = Array.from(name);
  for (let k = 1; k < n.length; k++) {
    if (body.endsWith(n.slice(0, k).join(''))) return `ends with partial name 「${n.slice(0, k).join('')}」`;
  }
  const two = n.slice(0, 2).join('');
  for (let i = body.indexOf(two); i >= 0; i = body.indexOf(two, i + 1)) {
    if (!body.startsWith(name, i)) return `partial name at ${i}`;
  }
  return null;
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    for (const lang of ['ko', 'ja', 'en', 'zh']) {
      // 前提：第 60 字確實落在名稱中間
      const src = Array.from(cardsFor(lang)[0].fields['互補性']);
      assert.ok(src.length > 60 && src.slice(START, START + Array.from(NAME).length).join('') === NAME, `${lang}: fixture`);
      const page = await browser.newPage({viewport: {width: 1280, height: 900}});
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(`http://127.0.0.1:${port}`);
      const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
      const base = {task_id: `task-cap-${lang}`, projects, a: 'a', targets, min_targets: 2, max_targets: 4, progress: [], error: null,
                    cards: [], card_state: {}, ...(lang === 'zh' ? {} : {lang})};
      const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
      await push({...base, status: 'loading', result: null}, false);
      const panel = page.frameLocator('#tangle-ws iframe');
      await panel.locator('[data-match-task]').waitFor();
      await push({...base, status: 'done', result, cards: cardsFor(lang)});
      const read = t => panel.locator(`[data-match-card="${t}"] [data-why-conclusion]`).textContent();
      await panel.locator('[data-match-card="c"] [data-why-conclusion]').waitFor();
      const b = (await read('b')).trim();
      const c = (await read('c')).trim();
      const bad = brokenName(b, NAME);
      ok(!bad && b.endsWith('…') && Array.from(b).length <= 60 && !b.includes('[測') ,
        `(a) lang=${lang}: name not cut (${bad || 'ok'}): 「${b}」`);
      ok(b.replace(/…$/, '') === lead(lang).trimEnd(), `(a) lang=${lang}: cut right before the name`);
      ok(c === LONG_NAME + '…',
        `(b) lang=${lang}: name at sentence start kept whole: 「${c}」`);
      assert.deepEqual(errors, [], `${lang}: page errors`);
      await page.close();
    }
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
