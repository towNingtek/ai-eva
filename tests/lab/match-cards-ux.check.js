// #231 媒合建議卡看得清楚：真實 overlay（public/tangle-lab-overlay.js）＋ 真實 embed.html?mode=match&v=live-match
// （照 app/apps/match_analysis/embed_route.py 補上 match-task.js、match-cards.js），推一份假結果：
// 一張有內容的卡（「為何推薦」是程式組的長字串，含規則原文）、一張四欄全「不足」的卡。
// (a) 卡片內所有可見文字（逐元素，含按鈕、CSS 畫出的鈕字）前景／背景對比 ≥ 4.5:1（收起、展開兩種狀態都量）
// (b) 有內容的卡：捲到卡片頂端時，第一屏看得到結論句（≤ 60 字）與按鈕列（在結論下方、其他欄位上方）；
//     規則原文預設看不到，展開「看依據」後看得到規則名稱、原文引用與底部「規則說明」
// (c) 全「不足」的卡只有一句說明＋「請對方補資料」（送 card_action op=supplement），畫面上「不足」0 個
// (d)「寄站內邀請」是唯一的實心主要按鈕
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

const names = {a: '大庄社區', b: '農產合作社', c: '青年團隊'};
const targets = ['b', 'c'];
const projects = Object.entries(names).map(([uuid, name]) => ({uuid, name}));
const KEYS = {B1: '空間與場域', B7: '市場與通路'};
const side = pid => ({pid, name: names[pid], match: Object.fromEntries(Object.keys(KEYS).map(k => [k, {role: 'none', evidence: []}]))});
const result = {
  demo: false, note: '本次真實判斷（測試資料）', keys: KEYS, a: 'a', not_evaluated: [],
  projects: ['a', ...targets].map(side),
  pairs: targets.map(pb => ({pa: 'a', pb, pair: ['a', pb].sort().join('|'), status: 'EXPLORE', status_text: '可探索',
    relations: {}, counts: {complement: 1, third: 0, peer: 0}, next_question: null})),
};
// 與 app/matching/cards.py _why 相同格式的長「為何推薦」（約 400 字、含規則原文）。
const RULE_ORIG = '雙方各自至少有一項「需要」能由對方的「能提供」滿足時，視為雙向互補，排序優先於只有單向互補的組合；' +
  '若雙方互補的能力類別數相同，再比較原文依據的段落數，段落越多越前面，仍相同時依使用者選擇對象的順序排列。';
const LONG_WHY = `依規則「雙向互補優先」（規則原文：${RULE_ORIG}），本組結果為雙向互補；` +
  `依規則「互補類別數」（規則原文：互補的能力類別越多，排序越前面，類別名稱以計畫理念原文能對應到的為準。），本組結果為2 類。` +
  '對應原文——市場與通路：大庄社區原文「需要行銷通路協助販售農產品」，農產合作社原文「有通路可以協助販售」；' +
  '空間與場域：農產合作社原文「缺少舉辦市集的場地」，大庄社區原文「社區活動中心可以借用」。' +
  '排在第 1 名，依據規則「雙向互補優先」。';
const NE = {'議題與目標對象': '未評估', '合作可執行性': '未評估', '跨國語境與成本': '未評估', '階段與時程': '未評估'};
const COMPLEMENT = '大庄社區需要的市場與通路，農產合作社能提供；農產合作社需要的空間與場域，大庄社區能提供。之後可再擴大到觀光導覽。';
const full = {
  rank: 1, target: 'b', name: names.b,
  fields: {
    '為何推薦': LONG_WHY, '互補性': COMPLEMENT,
    '互惠價值': '雙向互惠：大庄社區得到市場與通路的支援，農產合作社得到空間與場域的支援。',
    '建議合作': '先在社區活動中心辦一場小型農產市集，由合作社負責銷售。',
    '待確認': '活動中心週末是否可借用？', '風險': '雙方人力都有限，時程可能不同步。',
  },
  '未評估': NE,
  '原文段落': [{'計畫': names.a, '段落': 1, '原文': '需要行銷通路協助販售農產品'},
               {'計畫': names.b, '段落': 2, '原文': '有通路可以協助販售'}],
  '合作起步草案': null,
};
const thin = {
  rank: 2, target: 'c', name: names.c,
  fields: {'為何推薦': '不足', '互補性': '不足', '互惠價值': '不足', '建議合作': '不足', '待確認': '不足', '風險': '不足'},
  '未評估': NE, '原文段落': [], '合作起步草案': null,
};

// 頁面內：可見性（扣掉被 overflow 裁掉、在視窗外的部分）、對比計算、實心按鈕判斷。
const HELPERS = () => {
  const parse = c => {
    const m = String(c).match(/rgba?\(([^)]+)\)/);
    if (!m) return [0, 0, 0, 0];
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const over = (top, bottom) => {
    const a = top[3] + bottom[3] * (1 - top[3]);
    if (!a) return [0, 0, 0, 0];
    return [0, 1, 2].map(i => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a).concat(a);
  };
  const lum = ([r, g, b]) => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const ratio = (x, y) => { const [a, b] = [lum(x), lum(y)].sort((p, q) => q - p); return (a + 0.05) / (b + 0.05); };
  // 背景：由自己往上疊合，直到不透明。
  const background = el => {
    const layers = [];
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c[3] > 0) layers.push(c);
      if (c[3] >= 1) break;
    }
    let out = [255, 255, 255, 1];
    for (const c of layers.reverse()) out = over(c, out);
    return out;
  };
  const visibleRect = el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility !== 'visible' || el.closest('[hidden]')) return null;
    let r = el.getBoundingClientRect();
    let box = {l: r.left, t: r.top, r: r.right, b: r.bottom};
    for (let p = el.parentElement; p; p = p.parentElement) {
      const ps = getComputedStyle(p);
      if (ps.overflowX !== 'visible' || ps.overflowY !== 'visible') {
        const q = p.getBoundingClientRect();
        box = {l: Math.max(box.l, q.left), t: Math.max(box.t, q.top), r: Math.min(box.r, q.right), b: Math.min(box.b, q.bottom)};
      }
    }
    box = {l: Math.max(box.l, 0), t: Math.max(box.t, 0), r: Math.min(box.r, innerWidth), b: Math.min(box.b, innerHeight)};
    return box.r - box.l > 1 && box.b - box.t > 1 ? box : null;
  };
  // 會被看到的文字元素：自己有文字節點，或 ::before／::after 畫出字。
  const ownText = el => {
    const t = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim();
    const gen = ['::before', '::after'].map(p => getComputedStyle(el, p).content).filter(c => c && c !== 'none' && c !== 'normal');
    return t || (gen.length ? (el.getAttribute('data-label') || gen.join(' ')) : '');
  };
  const textOf = el => {
    // 在視窗外的元素：先不管視窗，只看是否被 overflow 裁掉（對比要逐元素全量）
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility !== 'visible') return null;
    return ownText(el);
  };
  const contrastIn = rootEl => {
    const rows = [];
    for (const el of [rootEl, ...rootEl.querySelectorAll('*')]) {
      const t = textOf(el);
      if (!t) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      // 被 overflow 裁到看不見的（收起的依據）不算可見
      let clipped = false;
      for (let p = el.parentElement; p && p !== rootEl.parentElement; p = p.parentElement) {
        const ps = getComputedStyle(p);
        if (ps.overflowY !== 'visible') { const q = p.getBoundingClientRect(); if (q.height < 1 || r.top >= q.bottom || r.bottom <= q.top) clipped = true; }
      }
      if (clipped) continue;
      let opacity = 1;
      for (let n = el; n; n = n.parentElement) opacity *= Number(getComputedStyle(n).opacity);
      const bg = background(el);
      const fg = parse(getComputedStyle(el).color);
      const shown = over([fg[0], fg[1], fg[2], fg[3] * opacity], bg);
      rows.push({text: t.slice(0, 30), tag: el.tagName.toLowerCase(), ratio: Math.round(ratio(shown, bg) * 100) / 100});
    }
    return rows;
  };
  const solid = b => {
    const c = parse(getComputedStyle(b).backgroundColor);
    return c[3] > 0.5 && lum(c) < 0.6;
  };
  window.__ux = {visibleRect, contrastIn, solid, ownText};
};

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch();
  let checks = 0;
  const ok = (cond, msg) => { assert.ok(cond, msg); checks++; console.log('ok', msg); };
  try {
    const page = await browser.newPage({viewport: {width: 1440, height: 900}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(() => {
      window.events = [];
      window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); });
    });
    const call = args => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail: {name: 'tangle_workspace', args}})), args);
    const push = (matchTask, update = true) => call({mode: 'match', v: 'live-match', matchTask, ...(update ? {update: true} : {})});
    const base = {task_id: 'task-ux', projects, a: 'a', targets, min_targets: 2, max_targets: 4, progress: [], error: null,
                  cards: [], card_state: {}};
    await push({...base, status: 'loading', result: null}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.locator('[data-match-task]').waitFor();
    await push({...base, status: 'done', result, cards: [full, thin]});
    const cardB = panel.locator('[data-match-card="b"]');
    const cardC = panel.locator('[data-match-card="c"]');
    await cardB.waitFor();
    await cardC.waitFor();
    const frame = page.frames().find(f => /embed\.html\?.*mode=match/.test(f.url()));
    await frame.evaluate(HELPERS);

    // (a) 對比：收起狀態
    const measure = async label => {
      const rows = await frame.evaluate(() => [...document.querySelectorAll('[data-match-card]')].flatMap(c => __ux.contrastIn(c)));
      assert.ok(rows.length >= 8, `${label}: measured text elements (${rows.length})`);
      const bad = rows.filter(r => r.ratio < 4.5);
      assert.deepEqual(bad, [], `${label}: contrast < 4.5 → ${JSON.stringify(bad)}`);
      const min = Math.min(...rows.map(r => r.ratio));
      ok(true, `(a) ${label}: ${rows.length} visible text elements in cards (incl. buttons), min contrast ${min}:1 ≥ 4.5`);
      return rows;
    };
    const rowsCollapsed = await measure('collapsed');
    ok(rowsCollapsed.some(r => r.tag === 'button' && r.text.includes('寄站內邀請'))
      && rowsCollapsed.some(r => r.tag === 'button' && r.text.includes('請對方補資料')), '(a) buttons are part of the contrast check');

    // (b) 有內容的卡：第一屏
    await cardB.evaluate(el => el.scrollIntoView({block: 'start'}));
    await page.waitForTimeout(100);
    const first = await cardB.evaluate(card => {
      const q = s => card.querySelector(s);
      const vr = el => el && __ux.visibleRect(el);
      const conclusion = q('[data-why-conclusion]');
      const actions = q('.mc-actions');
      const dl = q('dl');
      const rect = el => el.getBoundingClientRect();
      return {
        conclusion: conclusion?.textContent || '',
        conclusionShown: !!vr(conclusion),
        actionsShown: !!vr(actions) && [...actions.querySelectorAll('button')].every(b => vr(b)),
        actionsBelowConclusion: rect(actions).top >= rect(conclusion).bottom - 1,
        actionsAboveFields: !dl || rect(actions).bottom <= rect(dl).top + 1,
        ruleShown: [...card.querySelectorAll('[data-why-rule], [data-why-rule] *, [data-why-rules], [data-why-quotes] p')].some(el => vr(el)),
        leadHasRule: (q('.mc-lead')?.textContent || '').includes('規則原文'),
        visibleText: [...card.querySelectorAll('*')].filter(el => __ux.ownText(el) && vr(el)).map(el => __ux.ownText(el)).join('\n'),
      };
    });
    ok(first.conclusion.length > 0 && Array.from(first.conclusion).length <= 60, `(b) conclusion ≤ 60 chars: 「${first.conclusion}」`);
    ok(first.conclusion === COMPLEMENT.split('；')[0].slice(0, 59) + '…' || COMPLEMENT.startsWith(first.conclusion.replace(/…$/, '')),
      '(b) conclusion comes from the first sentence of 互補性');
    ok(first.conclusionShown && first.actionsShown, '(b) conclusion and the button row are on the first screen');
    ok(first.actionsBelowConclusion && first.actionsAboveFields, '(b) button row sits right under the conclusion, above the other fields');
    ok(!first.ruleShown && !first.leadHasRule && !first.visibleText.includes('規則原文') && !first.visibleText.includes(RULE_ORIG.slice(0, 20)),
      '(b) rule text and quotes are hidden by default');
    const toggle = cardB.getByRole('button', {name: '看依據'});
    ok(await toggle.count() === 1 && await toggle.getAttribute('aria-expanded') === 'false', '(b) 「看依據」 toggle present, collapsed');
    await toggle.click();
    await page.waitForTimeout(100);
    const opened = await cardB.evaluate(card => {
      const vr = el => el && __ux.visibleRect(el);
      card.querySelector('[data-why-rule]')?.scrollIntoView({block: 'center'});
      const quotes = [...card.querySelectorAll('[data-why-quotes] p')];
      const rule = card.querySelector('[data-why-rule] [data-field="為何推薦"]');
      const rules = card.querySelector('[data-why-rules]');
      const order = [rules, card.querySelector('[data-why-quotes]'), card.querySelector('[data-why-rule]')].map(e => e?.getBoundingClientRect().top);
      return {
        expanded: card.querySelector('[data-why-toggle]').getAttribute('aria-expanded'),
        quotes: quotes.filter(p => vr(p)).map(p => p.textContent),
        rules: vr(rules) ? rules.textContent : '',
        rule: vr(rule) ? rule.textContent : '',
        ruleSmall: rule ? parseFloat(getComputedStyle(rule).fontSize) < parseFloat(getComputedStyle(card.querySelector('[data-why-conclusion]')).fontSize) : false,
        ordered: order.every((t, i) => t != null && (i === 0 || t >= order[i - 1])),
      };
    });
    ok(opened.expanded === 'true' && opened.quotes.length === 2 && opened.quotes[0].includes('需要行銷通路協助販售農產品'),
      '(b) after 「看依據」 the original-text quotes are visible');
    ok(opened.rules.includes('雙向互補優先') && opened.rules.includes('互補類別數'), '(b) layer 2 names the rules');
    ok(opened.rule.includes(RULE_ORIG) && opened.ruleSmall && opened.ordered,
      '(b) layer 3: full rule text in small print at the bottom of layer 2');
    await measure('expanded');
    ok(await cardB.getByRole('button', {name: '收起依據'}).count() === 1, '(b) toggle now reads 收起依據');

    // (c) 全「不足」的卡
    await cardC.evaluate(el => el.scrollIntoView({block: 'start'}));
    const thinView = await cardC.evaluate(card => ({
      lines: card.innerText.split('\n').map(s => s.trim()).filter(Boolean),
      buttons: [...card.querySelectorAll('button')].map(b => b.textContent.trim()),
    }));
    ok(JSON.stringify(thinView.lines) === JSON.stringify(['2. 青年團隊', '這一案的計畫理念資訊太少，還無法判斷能怎麼合作', '請對方補資料'])
      && JSON.stringify(thinView.buttons) === JSON.stringify(['請對方補資料']),
      `(c) thin card shows only one sentence + 請對方補資料: ${JSON.stringify(thinView.lines)}`);
    const screen = await panel.locator('[data-match-cards]').evaluate(el => el.innerText);
    ok(!screen.includes('不足'), '(c) no 「不足」 on screen');
    await cardC.getByRole('button', {name: '請對方補資料'}).click();
    await page.waitForFunction(() => events.some(e => e.action === 'card_action'));
    assert.deepEqual(await page.evaluate(() => events.filter(e => e.action === 'card_action')),
      [{kind: 'match_task', action: 'card_action', task_id: 'task-ux', op: 'supplement', target: 'c'}]);
    ok(true, '(c) 請對方補資料 sends the existing card_action {op:supplement}');

    // (d) 實心主要按鈕
    const solids = await frame.evaluate(() => [...document.querySelectorAll('[data-match-card] button')]
      .filter(b => __ux.solid(b)).map(b => ({card: b.closest('[data-match-card]').dataset.matchCard, text: b.textContent.trim(), invite: b.hasAttribute('data-card-invite')})));
    ok(JSON.stringify(solids) === JSON.stringify([{card: 'b', text: '寄站內邀請', invite: true}]),
      `(d) 寄站內邀請 is the only solid primary button: ${JSON.stringify(solids)}`);
    const firstBtn = await cardB.evaluate(card => {
      const bs = [...card.querySelectorAll('.mc-actions button')].sort((x, y) => x.getBoundingClientRect().left - y.getBoundingClientRect().left);
      return bs[0]?.textContent.trim();
    });
    ok(firstBtn === '寄站內邀請', '(d) primary button leads the button row');

    // 寄邀請仍走確認框
    await cardB.getByRole('button', {name: '寄站內邀請'}).click();
    const dialog = panel.locator('[data-invite-confirm="b"]');
    await dialog.waitFor();
    const dlgBad = await frame.evaluate(() => __ux.contrastIn(document.querySelector('.mc-dialog > div')).filter(r => r.ratio < 4.5));
    assert.deepEqual(dlgBad, []);
    await dialog.getByRole('button', {name: '取消'}).click();
    ok(await page.evaluate(() => !events.some(e => e.action === 'invite')), 'invite still needs the confirmation dialog (dark text on white)');

    assert.deepEqual(errors, []);
    console.log(`checks ${checks}`);
    console.log('PASS');
  } finally {
    await browser.close();
    server.close();
  }
})().catch(e => { console.error(e); process.exit(1); });
