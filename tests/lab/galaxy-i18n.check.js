// #249 媒合星球頁（public/tangle/tangle-match.html 的 liveMatch=1 真實媒合模式）依使用者語言顯示。
// 走真實 overlay（public/tangle-lab-overlay.js）＋ embed.html?mode=match&v=live-match（照 embed_route.py 補 match-task.js、
// match-cards.js）＋ 巢狀星球 iframe；推一份真實形狀的判斷結果：B1–B8 衛星含 需要／能提供／需要＋能提供／沒有對象，
// 加上兩兩配對、關係與狀態。每個語言在星球 frame 裡依序收集：總覽 → 點選 A／B／C（狀態標籤、第三方與共同提供線）
// → 走進一對（互補）→ 返回 → 走進共同提供 → 返回；另走一次「A＋1 個對象」（兩星系狀態標籤）。
// 收集範圍：body 可見文字、可見 SVG <text>、可見元素的 aria-label／title／placeholder。
// 扣掉假資料中的專案名稱與原文後：en／ko 不得有漢字；ja 不得有中文專用字形、也不得有「長句無假名」（依假名比例判斷）。
// lang 來源：en、ja 由任務狀態帶 lang（en 另放 ja cookie，確認任務狀態優先）；ko 只靠 eva_lang cookie。
// lang＝zh（不帶 lang、無 cookie）時星球頁文字與改動前完全相同（ZH_BASELINE 以 --dump 在改動前取得）。
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
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript; charset=utf-8' : file.endsWith('.html') ? 'text/html; charset=utf-8'
      : file.endsWith('.css') ? 'text/css' : file.endsWith('.json') ? 'application/json' : file.endsWith('.png') ? 'image/png'
      : file.endsWith('.svg') ? 'image/svg+xml' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});

// ── 假資料：專案名稱與計畫原文是使用者資料（不翻）。B1–B8 名稱是伺服器給的 keys（zh）；頁面依語言自己換。
const names = {a: '溪畔社區', b: '竹藝工坊', c: '青農合作社'};
const KEYS = {B1: '空間與場域', B2: '產品與生產', B3: '服務與體驗', B4: '內容與品牌', B5: '人才與專業', B6: '社群與關係', B7: '市場與通路', B8: '治理與平台'};
const roles = {
  a: {B1: 'need', B2: 'offer', B3: 'both', B4: 'need', B5: 'offer', B7: 'need'},
  b: {B1: 'offer', B2: 'need', B3: 'offer', B4: 'need', B5: 'offer', B6: 'need', B8: 'both'},
  c: {B3: 'need', B4: 'need', B5: 'offer', B7: 'offer', B8: 'offer'},
};
const quote = (pid, k) => `${names[pid]}計畫原文第${k.slice(1)}段`;
const QUOTES = Object.keys(names).flatMap(pid => Object.keys(KEYS).map(k => quote(pid, k)));
const DATA = [...Object.values(names), ...QUOTES];
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k =>
  [k, {role: roles[pid][k] || 'none', evidence: roles[pid][k] ? [quote(pid, k)] : []}]))});
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const STATUS = {b: ['CLARIFY_FIRST', '先補資料'], c: ['EXPLORE', '可探索']};
const resultFor = targets => ({
  demo: false, keys: KEYS, a: 'a', not_evaluated: [],
  note: 'B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。',
  projects: ['a', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: STATUS[pb][0], status_text: STATUS[pb][1],
    relations: {complement: ['B1', 'B2'], third: ['B4'], peer: ['B5']}, counts: {complement: 2, third: 1, peer: 1}, next_question: null})),
});

const HAN = /[㐀-鿿豈-﫿]/;
const KANA = /[぀-ヿ]/;
const CN_ONLY = /[們這會為與對說號關讀從還經實寫錄邀狀專畫處應來嗎您讓麼將个们这会为与对说号关读从还经实写录邀状专画处应来吗让么将选择项确认补资时间开启请體與]/;
const strip = s => DATA.slice().sort((x, y) => y.length - x.length).reduce((t, d) => t.split(d).join(''), s);
function violations(lang, texts) {
  const bad = [];
  for (const raw of texts) {
    const t = strip(raw);
    if (lang === 'ja') {
      if (CN_ONLY.test(t)) bad.push(`中文字形: ${raw}`);
      for (const piece of t.split(/[\n。！？!?：:・]/)) {
        const han = (piece.match(new RegExp(HAN.source, 'g')) || []).length;
        const kana = (piece.match(new RegExp(KANA.source, 'g')) || []).length;
        if (han >= 4 && piece.trim().length >= 8 && !kana) bad.push(`長句無假名: ${piece.trim()}`);
        if (han >= 3 && kana * 4 < han) bad.push(`假名過少: ${piece.trim()}`);
      }
    } else if (HAN.test(t)) bad.push(`漢字: ${raw}`);
  }
  return bad;
}

// 星球 frame 內：body 可見文字＋可見 SVG <text>＋可見元素的 aria-label／title／placeholder。排序後比較。
function collectGalaxy() {
  const out = [];
  const visible = el => {
    if (el.closest('[hidden]')) return false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || +cs.opacity === 0) return false;
      if (n.getAttribute('opacity') === '0') return false;
    }
    return el.getClientRects().length > 0 || getComputedStyle(el).position === 'fixed';
  };
  out.push(...(document.body.innerText || '').split('\n').map(s => s.trim()).filter(Boolean).map(s => `text: ${s}`));
  for (const t of document.querySelectorAll('svg text')) if (visible(t) && t.textContent.trim()) out.push(`svg: ${t.textContent.trim()}`);
  for (const el of document.querySelectorAll('*')) {
    if (!visible(el)) continue;
    for (const at of ['aria-label', 'title', 'placeholder']) if (el.getAttribute(at)) out.push(`[${at}] ${el.getAttribute(at)}`);
  }
  return [...new Set(out)].sort();
}

async function walk(browser, port, {snapshotLang, cookie, targets}) {
  const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}, reducedMotion: 'reduce'});
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
  const panel = page.frameLocator('#tangle-ws iframe');
  const base = {task_id: 'task-249', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null,
    cards: [], card_state: {}};
  const steps = {};
  try {
    await push({...base, status: 'loading'}, false);
    await panel.locator('[data-match-task]').waitFor();
    await page.waitForFunction(() => events.some(e => e.action === 'get'));
    await push({...base, status: 'done', projects, a: 'a', targets, result: resultFor(targets)});
    await panel.locator('iframe[data-match-galaxy]').waitFor();
    const gal = () => page.frames().find(f => /tangle-match\.html\?liveMatch=1/.test(f.url()));
    for (let i = 0; i < 80 && !(gal() && await gal().evaluate(() => !!document.getElementById('zFit') && !!document.querySelector('[data-kv-key]')).catch(() => false)); i++) await page.waitForTimeout(100);
    const g = gal();
    assert.ok(g, 'galaxy frame loaded');
    const src = await panel.locator('iframe[data-match-galaxy]').getAttribute('src');
    await page.waitForTimeout(1500);
    const collect = async (step, wait = 900) => { await page.waitForTimeout(wait); steps[step] = await g.evaluate(collectGalaxy); };
    await collect('overview', 0);
    const n = targets.length + 1;
    for (let id = 1; id <= n; id++) {
      await g.evaluate(id => { focus = id; if (typeof sel !== 'undefined') sel = null; syncMode(); draw(); }, id);
      await collect(`focus${id}`);
    }
    await g.evaluate(() => { focus = null; syncMode(); draw(); });
    await g.evaluate(() => mfEnter('B1', 'pair', byId(1), byId(2)));
    await collect('pair');
    await g.evaluate(() => mfLeave());
    await page.waitForTimeout(900);
    await g.evaluate(() => mfEnter('B5', 'peer', byId(1), byId(2)));
    await collect('peer');
    await g.evaluate(() => mfLeave());
    await collect('back');
    const htmlLang = await g.evaluate(() => document.documentElement.lang);
    assert.deepEqual(errors, [], 'page errors');
    return {steps, src, htmlLang};
  } finally { await ctx.close(); }
}

// lang＝zh 星球頁文字（改動前 epic/205-bee-249 6c21471 以 --dump 取得；每步排序、去重）。
const ZH_BASELINE = {
 "three": {
  "overview": [
   "[aria-label] 人才與專業",
   "[aria-label] 內容與品牌",
   "[aria-label] 市場與通路",
   "[aria-label] 市場與通路：有依據的關係",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 治理與平台：有依據的關係",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・能提供",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・能提供",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "svg: 青農合作社",
   "text: 100%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 內容與品牌・需要",
   "text: 市場與通路・能提供",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・能提供",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: 青農合作社",
   "text: ＋"
  ],
  "focus1": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：竹藝工坊：先補資料",
   "[aria-label] 媒合狀態：青農合作社：可探索",
   "[aria-label] 市場與通路",
   "[aria-label] 市場與通路：有依據的關係",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 可探索",
   "svg: 市場與通路・能提供",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・能提供",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "svg: 青農合作社",
   "text: 100%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 可探索",
   "text: 市場與通路・能提供",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・能提供",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: 青農合作社",
   "text: ＋"
  ],
  "focus2": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：溪畔社區：先補資料",
   "[aria-label] 媒合狀態：青農合作社：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 治理與平台：有依據的關係",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・能提供",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・能提供",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "svg: 青農合作社",
   "text: 100%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 市場與通路・能提供",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・能提供",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: 青農合作社",
   "text: ＋"
  ],
  "focus3": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：溪畔社區：可探索",
   "[aria-label] 媒合狀態：竹藝工坊：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 市場與通路：有依據的關係",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 治理與平台：有依據的關係",
   "[aria-label] 產品與生產",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 可探索",
   "svg: 市場與通路・能提供",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・能提供",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "svg: 青農合作社",
   "text: 100%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 可探索",
   "text: 市場與通路・能提供",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・能提供",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: 青農合作社",
   "text: ＋"
  ],
  "pair": [
   "[title] 重設",
   "svg: 1 段原文",
   "svg: 互補候選：能提供 → 需要",
   "svg: 溪畔社區",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 1 段原文",
   "text: 100%",
   "text: ← 返回兩個星系",
   "text: −",
   "text: ⛶",
   "text: 互補候選：能提供 → 需要",
   "text: 溪畔社區",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "peer": [
   "[title] 重設",
   "svg: 1 段原文",
   "svg: 人才與專業・能提供",
   "svg: 兩邊都能提供：可聯合或交流（需另判競合）",
   "svg: 溪畔社區",
   "svg: 竹藝工坊",
   "text: 1 段原文",
   "text: 100%",
   "text: ← 返回兩個星系",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 兩邊都能提供：可聯合或交流（需另判競合）",
   "text: 溪畔社區",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "back": [
   "[aria-label] 人才與專業",
   "[aria-label] 內容與品牌",
   "[aria-label] 市場與通路",
   "[aria-label] 市場與通路：有依據的關係",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 治理與平台：有依據的關係",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・能提供",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・能提供",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "svg: 青農合作社",
   "text: 100%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 內容與品牌・需要",
   "text: 市場與通路・能提供",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・能提供",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: 青農合作社",
   "text: ＋"
  ]
 },
 "two": {
  "overview": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 120%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "focus1": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 120%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "focus2": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 120%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "pair": [
   "[title] 重設",
   "svg: 1 段原文",
   "svg: 互補候選：能提供 → 需要",
   "svg: 溪畔社區",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 1 段原文",
   "text: 120%",
   "text: ← 返回兩個星系",
   "text: −",
   "text: ⛶",
   "text: 互補候選：能提供 → 需要",
   "text: 溪畔社區",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "peer": [
   "[title] 重設",
   "svg: 1 段原文",
   "svg: 人才與專業・能提供",
   "svg: 兩邊都能提供：可聯合或交流（需另判競合）",
   "svg: 溪畔社區",
   "svg: 竹藝工坊",
   "text: 1 段原文",
   "text: 120%",
   "text: ← 返回兩個星系",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 兩邊都能提供：可聯合或交流（需另判競合）",
   "text: 溪畔社區",
   "text: 竹藝工坊",
   "text: ＋"
  ],
  "back": [
   "[aria-label] 人才與專業",
   "[aria-label] 人才與專業：兩邊都能提供",
   "[aria-label] 內容與品牌",
   "[aria-label] 內容與品牌：兩邊都需要",
   "[aria-label] 媒合狀態：先補資料",
   "[aria-label] 市場與通路",
   "[aria-label] 服務與體驗",
   "[aria-label] 服務與體驗：有依據的關係",
   "[aria-label] 治理與平台",
   "[aria-label] 產品與生產",
   "[aria-label] 產品與生產：有依據的關係",
   "[aria-label] 社群與關係",
   "[aria-label] 空間與場域",
   "[aria-label] 空間與場域：有依據的關係",
   "[title] 重設",
   "svg: 人才與專業・能提供",
   "svg: 先補資料",
   "svg: 內容與品牌・需要",
   "svg: 市場與通路・需要",
   "svg: 服務與體驗・能提供",
   "svg: 服務與體驗・需要＋能提供",
   "svg: 沒有對象",
   "svg: 治理與平台・需要＋能提供",
   "svg: 溪畔社區",
   "svg: 產品與生產・能提供",
   "svg: 產品與生產・需要",
   "svg: 社群與關係・需要",
   "svg: 空間與場域・能提供",
   "svg: 空間與場域・需要",
   "svg: 竹藝工坊",
   "text: 120%",
   "text: −",
   "text: ⛶",
   "text: 人才與專業・能提供",
   "text: 先補資料",
   "text: 內容與品牌・需要",
   "text: 市場與通路・需要",
   "text: 服務與體驗・能提供",
   "text: 服務與體驗・需要＋能提供",
   "text: 沒有對象",
   "text: 治理與平台・需要＋能提供",
   "text: 溪畔社區",
   "text: 產品與生產・能提供",
   "text: 產品與生產・需要",
   "text: 社群與關係・需要",
   "text: 空間與場域・能提供",
   "text: 空間與場域・需要",
   "text: 竹藝工坊",
   "text: ＋"
  ]
 }
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  const scenarios = {three: ['b', 'c'], two: ['b']};
  try {
    const zh = {};
    for (const [sc, targets] of Object.entries(scenarios)) zh[sc] = await walk(browser, port, {targets});
    const zhSteps = Object.fromEntries(Object.entries(zh).map(([k, v]) => [k, v.steps]));
    if (process.argv.includes('--dump')) { console.log(JSON.stringify(zhSteps, null, 1)); return; }
    assert.ok(ZH_BASELINE, 'ZH_BASELINE missing');
    assert.deepEqual(zhSteps, ZH_BASELINE, 'lang=zh galaxy text unchanged');
    ok(true, 'lang=zh: planet page text identical to the pre-change baseline (3 and 2 planets, all steps)');
    ok(zh.three.htmlLang === 'zh-Hant', 'lang=zh: <html lang> stays zh-Hant');
    const all = Object.values(zhSteps).flatMap(s => Object.values(s)).flat();
    ok(all.some(t => t.includes('空間與場域・需要')) && all.some(t => t.includes('沒有對象')), 'lang=zh: baseline has B1–B8 satellite labels (sanity)');

    const runs = [['en', {snapshotLang: 'en', cookie: 'ja'}], ['ja', {snapshotLang: 'ja', cookie: 'ja'}], ['ko', {cookie: 'ko'}]];
    for (const [lang, how] of runs) {
      for (const [sc, targets] of Object.entries(scenarios)) {
        const {steps, src, htmlLang} = await walk(browser, port, {...how, targets});
        if (process.argv.includes('--show')) console.log(lang, sc, JSON.stringify(steps, null, 1));
        assert.match(src, new RegExp(`[?&]lang=${lang}(&|$)`), `${lang}: iframe src carries lang`);
        assert.equal(htmlLang, lang, `${lang}: <html lang>`);
        for (const [step, texts] of Object.entries(steps)) {
          assert.ok(texts.length > 5, `${lang} ${sc} ${step}: collected text`);
          const bad = violations(lang, texts);
          assert.deepEqual(bad, [], `${lang} ${sc} ${step}: ${bad.join(' | ')}`);
        }
        const flat = Object.values(steps).flat().join('\n');
        assert.ok(flat.includes(names.a) && flat.includes(names.b), `${lang} ${sc}: project names kept as-is`);
        assert.equal(Object.keys(steps).length, Object.keys(zh[sc].steps).length, `${lang} ${sc}: same steps as zh`);
        for (const step of Object.keys(steps)) {
          const zl = zh[sc].steps[step].length, ll = steps[step].length;
          assert.ok(Math.abs(zl - ll) <= Math.max(2, zl * 0.15), `${lang} ${sc} ${step}: comparable amount of text (${ll} vs zh ${zl})`);
        }
        ok(true, `lang=${lang} (${how.snapshotLang ? 'task state' : 'cookie'}) ${sc === 'three' ? '3' : '2'} planets: ${Object.keys(steps).join(' → ')} has no Chinese text`);
      }
    }
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
