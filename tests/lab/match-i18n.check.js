// #226 外文通道：媒合星球工作區（match-task.js）與建議卡（match-cards.js）的介面文字依使用者語言顯示。
// lang＝en／ja／ko 各開一次面板，走「載入 → 選案 → 判斷中 → 判斷完成 → 建議卡 → 寄站內邀請確認框 → 已寄出」，
// 每一步收集面板可見文字與 aria-label／title／placeholder，扣掉假資料中的專案名稱與原文引用後：
//   en／ko 不得有漢字；ja 不得有中文專用字形、也不得有「長句無假名」。
// lang 來源：en、ja 由任務狀態帶 lang（en 同時放一個 ja cookie，確認任務狀態優先）；ko 只靠 eva_lang cookie。
// lang＝zh（不帶 lang、無 cookie）時每一步文字與改動前（beta 7a7b9c2）完全相同。
// 自己伺服 repo；Playwright 由 NODE_PATH 提供（找不到時退回 /tmp/pw/node_modules）。最後一行 PASS。
// 用 `--dump` 執行會印出 zh 各步文字（產生下方 ZH_BASELINE 用）。
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

// ── 假資料：專案名稱、計畫原文是使用者資料（不翻）；LLM 寫的卡片欄位內容依語言給（外文通道由 LLM 以使用者語言產生）。
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

const HAN = /[㐀-鿿豈-﫿]/;
const KANA = /[぀-ヿ]/;
// 日文不用、只出現在中文（繁／簡）的字形。
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

// lang＝zh 時每一步的面板文字（改動前 beta 7a7b9c2 以 --dump 取得）。
// #232：移除「更新進度」、加入步驟條後以 --dump 重新產生（差異僅此兩項，2026-11-23 PM 核對）。
const ZH_BASELINE = {
 "loading": [
  "[aria-label] 策略工作區",
  "專案媒合工作區",
  "載入專案清單中…"
 ],
 "select": [
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
 "pending": [
  "[aria-label] 策略工作區",
  "專案媒合工作區",
  "已送出，等待工作區更新…",
  "專案 A",
  "大庄社區",
  "農產合作社",
  "比較對象（2–4 個）",
  "大庄社區",
  "農產合作社",
  "青年團隊",
  "導覽協會",
  "開始媒合 →已選 0 個",
  "[aria-label] 專案 A"
 ],
 "running": [
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
 ],
 "confirm": [
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
  "[title] 本次媒合星系",
  "確定要寄站內邀請給「青年團隊」嗎？寄出後對方會收到通知。",
  "確定寄出",
  "取消"
 ],
 "sent": [
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
  "農產合作社\t可探索\t1\t0\t0\t星圖中 請 Eva 說明",
  "青年團隊\t先補資料\t1\t1\t0\t星圖中 請 Eva 說明",
  "導覽協會\t可排序・未建議\t1\t2\t0\t星圖中 請 Eva 說明",
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
  "已收藏・已略過・補充已寫回計畫理念",
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
  "已寄出邀請",
  "已寄出站內邀請",
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
  "已請 Eva 問補資料",
  "[title] 本次媒合星系"
 ],
 "error": [
  "[aria-label] 策略工作區",
  "專案媒合工作區",
  "媒合未完成",
  "讀取專案清單失敗（CMS 503），請按「開始新媒合」再試。",
  "開始新媒合"
 ]
};

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
  const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match',
    matchTask: snapshotLang ? {...matchTask, lang: snapshotLang} : matchTask, ...(update ? {update: true} : {})});
  const waitAction = action => page.waitForFunction(a => events.some(e => e.action === a), action);
  const panel = page.frameLocator('#tangle-ws iframe');
  const frame = () => page.frames().find(f => /embed\.html\?.*mode=match/.test(f.url()));
  const steps = {};
  const collect = async step => {
    await page.waitForTimeout(150);
    steps[step] = await frame().evaluate(() => {
      const out = [];
      // 面板＝工作區標頭（標題、對話／收合鈕）＋ 媒合任務面板（含建議卡）＋ 確認框；
      // 同一個 desk 裡雲林示範的分析表單（yunlin.js）不屬於這個面板。
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
    });
  };
  const base = {task_id: 'task-1', projects: [], a: null, targets: [], min_targets: 2, max_targets: 4, progress: [], result: null, error: null,
    cards: [], card_state: {}};
  try {
    await push({...base, status: 'loading'}, false);
    await panel.locator('[data-match-task]').waitFor();
    // 面板開好會發 get 取目前狀態；如伺服器般再推一次 loading 快照（第一推比 iframe 早到）。
    await waitAction('get');
    await push({...base, status: 'loading'});
    await collect('loading');
    await push({...base, status: 'select', projects, initiable: ['a', 'b']});
    await panel.locator('[data-match-start]').waitFor();
    await panel.locator('[data-match-a]').selectOption('a');
    for (const t of targets) await panel.locator(`[data-match-target="${t}"]`).check();
    await collect('select');
    await panel.locator('[data-match-start]').click();
    await waitAction('select');
    await collect('pending');
    await push({...base, status: 'running', projects, a: 'a', targets, progress: [{uuid: 'a', name: names.a, step: 'fetch'}]});
    await panel.locator('[data-match-steps] li').first().waitFor();  // #232 判斷中不再有「更新進度」按鈕，改等步驟條
    await collect('running');
    const done = {...base, status: 'done', projects, a: 'a', targets, result, cards: cardsFor(lang)};
    await push(done);
    await panel.locator('[data-match-cards] [data-match-card]').first().waitFor();
    await panel.locator('iframe[data-match-galaxy]').waitFor();
    await collect('done');
    await panel.locator('[data-match-card="c"] [data-card-invite]').click();
    await panel.locator('[data-invite-confirm="c"]').waitFor();
    await collect('confirm');
    await panel.locator('[data-invite-ok]').click();
    await waitAction('invite');
    await push({...done, card_state: {b: {favorite: true, skip: true, supplement: 'ok'}, c: {invite: 'sent'}, d: {supplement: true}}});
    await panel.locator('[data-match-card="c"] [data-card-state]').waitFor();
    await collect('sent');
    await push({...base, task_id: 'task-2', status: 'error', projects, error: '讀取專案清單失敗（CMS 503），請按「開始新媒合」再試。'});
    await panel.locator('[data-match-task] [role="alert"]').waitFor();
    await collect('error');
    assert.deepEqual(errors, [], `${lang}: page errors`);
    return steps;
  } finally { await ctx.close(); }
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    const zh = await walk(browser, port, 'zh', {});
    if (process.argv.includes('--dump')) { console.log(JSON.stringify(zh, null, 1)); return; }
    assert.ok(ZH_BASELINE, 'ZH_BASELINE missing');
    for (const step of Object.keys(ZH_BASELINE)) assert.deepEqual(zh[step], ZH_BASELINE[step], `zh step ${step} unchanged`);
    ok(Object.keys(zh).join() === Object.keys(ZH_BASELINE).join(), 'lang=zh: every step shows exactly the current text');

    const runs = [['en', {snapshotLang: 'en', cookie: 'ja'}], ['ja', {snapshotLang: 'ja', cookie: 'ja'}], ['ko', {cookie: 'ko'}]];
    for (const [lang, how] of runs) {
      const steps = await walk(browser, port, lang, how);
      for (const [step, texts] of Object.entries(steps)) {
        assert.ok(texts.length > 0, `${lang} ${step}: collected text`);
        const bad = violations(lang, texts);
        assert.deepEqual(bad, [], `${lang} ${step}: ${bad.join(' | ')}`);
      }
      const all = Object.values(steps).flat().join('\n');
      assert.ok(all.includes(names.a) && all.includes(QA), `${lang}: project names and quotes are kept as-is`);
      ok(true, `lang=${lang} (${how.snapshotLang ? 'task state' : 'cookie'}): ${Object.keys(steps).join(' → ')} has no Chinese UI text`);
    }

    // 字串表：四語鍵集合一致。
    const page = await browser.newPage();
    await page.goto(`http://127.0.0.1:${port}/public/workspace/embed.html?mode=match&v=live-match`);
    await page.waitForFunction(() => window.__MATCH_I18N && window.__MATCH_CARDS_I18N);
    const shape = await page.evaluate(() => {
      const keys = o => Object.keys(o).sort().flatMap(k => o[k] && typeof o[k] === 'object' && !Array.isArray(o[k])
        ? keys(o[k]).map(x => `${k}.${x}`) : [k]);
      return [window.__MATCH_I18N, window.__MATCH_CARDS_I18N].map(t => Object.fromEntries(Object.entries(t).map(([l, v]) => [l, keys(v).join()])));
    });
    await page.close();
    for (const table of shape) {
      assert.deepEqual(Object.keys(table).sort(), ['en', 'ja', 'ko', 'zh']);
      for (const l of ['en', 'ja', 'ko']) assert.equal(table[l], table.zh, `MATCH_I18N.${l} key set equals zh`);
    }
    ok(true, 'MATCH_I18N {zh,en,ja,ko} share one key set (panel and cards)');
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
