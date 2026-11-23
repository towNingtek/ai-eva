// #215 媒合建議卡：真實媒合任務（mode=match&v=live-match）判斷完成後，在任務面板下方畫出伺服器給的卡。
// 卡上只放白話（為何推薦＋原文段落、互補性…、未評估），不顯示 B 代號。
// 按鈕：收藏／略過／補資料 → match_task card_action；寄站內邀請 → 先開確認框，按「確定」才送 invite（confirmed:true）。
// AI 不會自己寄：這裡是唯一會送出 invite 的地方，而且只在使用者按下確認框的「確定」之後。
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get('mode') !== 'match' || q.get('v') !== 'live-match') return;
  const B_CODE = /\bB[1-8]\b/g;
  const clean = t => String(t ?? '').replace(B_CODE, '').replace(/\s{2,}/g, ' ').trim();
  const node = (tag, text, attrs) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent = clean(text);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    return el;
  };
  // #226 介面文字依使用者語言（任務狀態 lang 優先，其次 eva_lang cookie，預設 zh）。
  // 卡片欄位內容、專案名稱、計畫原文不翻；伺服器給的中文欄位名只換顯示標籤，data-field 保持原鍵。
  const MATCH_I18N = {
    zh: {
      ops: {favorite: '收藏', skip: '略過', supplement: '補資料'},
      state: {favorite: '已收藏', skip: '已略過', asked: '已請 Eva 問補資料', noted: '補充已記下',
        invite: {confirm: '等待確認寄出', sent: '已寄出站內邀請', error: '邀請沒有寄出'},
        supplement: {ok: '補充已寫回計畫理念', declined: '補充只留在紀錄', not_manageable: '補充已記下（不可寫回）'}},
      confirm: name => `確定要寄站內邀請給「${name}」嗎？寄出後對方會收到通知。`, ok: '確定寄出', cancel: '取消',
      invite: '寄站內邀請', invited: '已寄出邀請',
      fields: {'為何推薦': '為何推薦', '互補性': '互補性', '互惠價值': '互惠價值', '建議合作': '建議合作', '待確認': '待確認', '風險': '風險'},
      quote: (plan, n, text) => `${plan}・第 ${n} 段：「${text}」`, quoteLabel: '原文',
      notEvaluated: '未評估', insufficient: '不足', sep: '、', pair: (k, v) => `${k}：${v}`,
      dims: {'議題與目標對象': '議題與目標對象', '合作可執行性': '合作可執行性', '跨國語境與成本': '跨國語境與成本', '階段與時程': '階段與時程'},
      title: '媒合建議卡', note: '依這次判斷排出的建議；要不要聯絡、怎麼開始由你決定。寄站內邀請前會再請你確認。',
      basis: {show: '看依據', hide: '收起依據'}, rules: names => `依據規則：${names}`, ruleText: '規則說明',
      whyFallback: '符合媒合規則，可以先聊聊看。',
      thin: '這一案的計畫理念資訊太少，還無法判斷能怎麼合作', askInfo: '請對方補資料',
    },
    en: {
      ops: {favorite: 'Save', skip: 'Skip', supplement: 'Add details'},
      state: {favorite: 'Saved', skip: 'Skipped', asked: 'Asked Eva to collect more details', noted: 'Details noted',
        invite: {confirm: 'Waiting for you to confirm', sent: 'Site invitation sent', error: 'Invitation was not sent'},
        supplement: {ok: 'Details written back to the plan', declined: 'Details kept in the log only',
          not_manageable: 'Details noted (cannot be written back)'}},
      confirm: name => `Send a site invitation to "${name}"? They will be notified once it is sent.`, ok: 'Send', cancel: 'Cancel',
      invite: 'Send site invitation', invited: 'Invitation sent',
      fields: {'為何推薦': 'Why suggested', '互補性': 'Complementarity', '互惠價值': 'Mutual value', '建議合作': 'Suggested collaboration',
        '待確認': 'To confirm', '風險': 'Risks'},
      quote: (plan, n, text) => `${plan}, paragraph ${n}: "${text}"`, quoteLabel: 'Original text',
      notEvaluated: 'Not evaluated', insufficient: 'Insufficient', sep: ', ', pair: (k, v) => `${k}: ${v}`,
      dims: {'議題與目標對象': 'Issues and target groups', '合作可執行性': 'Feasibility', '跨國語境與成本': 'Cross-border context and cost',
        '階段與時程': 'Stage and timeline'},
      title: 'Matching suggestions', note: 'Suggestions ranked from this run. You decide whether and how to get in touch; we will ask you to confirm before any site invitation is sent.',
      basis: {show: 'See the basis', hide: 'Hide the basis'}, rules: names => `Rules applied: ${names}`, ruleText: 'About the rules',
      whyFallback: 'Meets the matching rules; worth a first conversation.',
      thin: 'This plan says too little about its philosophy to tell how you could work together yet', askInfo: 'Ask them to add details',
    },
    ja: {
      ops: {favorite: 'お気に入り', skip: 'スキップ', supplement: '情報を補う'},
      state: {favorite: 'お気に入り済み', skip: 'スキップ済み', asked: 'Eva に情報の補足を頼みました', noted: '補足を記録しました',
        invite: {confirm: '送信の確認待ち', sent: 'サイト内招待を送りました', error: '招待は送られませんでした'},
        supplement: {ok: '補足をプランの理念に書き戻しました', declined: '補足は記録のみに残しました', not_manageable: '補足を記録しました（書き戻しはできません）'}},
      confirm: name => `「${name}」にサイト内招待を送りますか？送ると相手に通知されます。`, ok: '送信する', cancel: 'キャンセル',
      invite: 'サイト内招待を送る', invited: '招待を送りました',
      fields: {'為何推薦': 'おすすめの理由', '互補性': '補完性', '互惠價值': '相互のメリット', '建議合作': '協力の提案', '待確認': '確認すること', '風險': 'リスク'},
      quote: (plan, n, text) => `${plan}・${n} 段落目：「${text}」`, quoteLabel: '原文',
      notEvaluated: '未評価', insufficient: '情報不足です', sep: '、', pair: (k, v) => `${k}：${v}`,
      dims: {'議題與目標對象': 'テーマと対象者', '合作可執行性': '協力の実行可能性', '跨國語境與成本': '国をまたぐ文脈とコスト', '階段與時程': '段階とスケジュール'},
      title: 'マッチングの提案カード', note: '今回の判定から並べた提案です。連絡するか、どう始めるかはあなたが決めます。サイト内招待を送る前にもう一度確認します。',
      basis: {show: '根拠を見る', hide: '根拠を閉じる'}, rules: names => `根拠のルール：${names}`, ruleText: 'ルールの説明',
      whyFallback: 'マッチングのルールに合っています。まず話してみましょう。',
      thin: 'この案は計画の理念の情報が少なすぎて、どう協力できるかまだ判断できません', askInfo: '相手に情報の補足をお願いする',
    },
    ko: {
      ops: {favorite: '즐겨찾기', skip: '건너뛰기', supplement: '정보 보완'},
      state: {favorite: '즐겨찾기함', skip: '건너뜀', asked: 'Eva에게 정보 보완을 요청함', noted: '보완 내용 기록됨',
        invite: {confirm: '보내기 확인 대기 중', sent: '사이트 내 초대를 보냄', error: '초대를 보내지 못함'},
        supplement: {ok: '보완 내용을 계획 이념에 반영함', declined: '보완 내용은 기록에만 남김', not_manageable: '보완 내용 기록됨(반영 불가)'}},
      confirm: name => `"${name}"에게 사이트 내 초대를 보낼까요? 보내면 상대방에게 알림이 갑니다.`, ok: '보내기', cancel: '취소',
      invite: '사이트 내 초대 보내기', invited: '초대를 보냄',
      fields: {'為何推薦': '추천 이유', '互補性': '보완성', '互惠價值': '상호 가치', '建議合作': '협력 제안', '待確認': '확인할 점', '風險': '위험'},
      quote: (plan, n, text) => `${plan}・${n}번째 단락: "${text}"`, quoteLabel: '원문',
      notEvaluated: '평가 안 함', insufficient: '정보 부족', sep: ', ', pair: (k, v) => `${k}: ${v}`,
      dims: {'議題與目標對象': '의제와 대상', '合作可執行性': '협력 실행 가능성', '跨國語境與成本': '국가 간 맥락과 비용', '階段與時程': '단계와 일정'},
      title: '매칭 제안 카드', note: '이번 판단으로 정렬한 제안입니다. 연락할지, 어떻게 시작할지는 직접 정하세요. 사이트 내 초대를 보내기 전에 다시 확인합니다.',
      basis: {show: '근거 보기', hide: '근거 접기'}, rules: names => `근거 규칙: ${names}`, ruleText: '규칙 설명',
      whyFallback: '매칭 규칙에 맞습니다. 먼저 이야기해 보세요.',
      thin: '이 안은 계획 이념 정보가 너무 적어 어떻게 협력할지 아직 판단할 수 없습니다', askInfo: '상대방에게 정보 보완 요청',
    },
  };
  window.__MATCH_CARDS_I18N = MATCH_I18N;
  const OPS = ['favorite', 'skip', 'supplement'];
  const LANG_ALIAS = {zh: 'zh', en: 'en', ja: 'ja', jp: 'ja', ko: 'ko', kr: 'ko'};
  const normLang = v => LANG_ALIAS[String(v || '').trim().toLowerCase().split(/[-_]/)[0]] || null;
  const cookieLang = () => {
    const m = document.cookie.match(/(?:^|;\s*)eva_lang=([^;]*)/);
    try { return m ? normLang(decodeURIComponent(m[1])) : null; } catch (_) { return null; }
  };
  let lang = 'zh', T = MATCH_I18N.zh;
  // 欄位值：伺服器固定的「不足」換成該語言；其餘是 LLM 依使用者語言寫的內容，照原樣。
  const valueText = v => (lang !== 'zh' && String(v).trim() === '不足' ? T.insufficient : v);

  let snapshot = null, wrap = null, dialog = null, key = null;
  const opened = new Set();  // 已展開「看依據」的卡（task_id|target），重畫時保留

  // #231 建議卡是白底：所有文字、按鈕都用深色，不沿用工作區深色主題的淺白字（#e5e5eb，對比 1.25:1）。
  // 版面：標題 → 一句結論 → 按鈕列（寄站內邀請為唯一實心主要按鈕）→「看依據」（規則名稱＋原文引用＋規則說明）→ 其他欄位。
  // DOM 依閱讀順序（結論、依據、欄位、按鈕），視覺順序用 flex order 把按鈕列提到結論下方。
  const style = document.createElement('style');
  style.textContent = `
    .live-match .mc-cards{display:flex;flex-direction:column;gap:10px}
    .live-match .mc-card{border:1px solid #d8dee6;border-radius:10px;padding:10px 12px;background:#fff;color:#1f2933;
      display:flex;flex-direction:column;gap:6px;line-height:1.6}
    .live-match .mc-card h4{margin:0;font-size:15px;color:#1f2933;order:0}
    .live-match .mc-lead{order:1}
    .live-match .mc-label{display:block;color:#52606d;font-size:12px}
    .live-match .mc-conclusion{margin:0;font-size:15px;font-weight:600;color:#1f2933}
    .live-match .mc-actions{display:flex;flex-wrap:wrap;gap:6px;order:2}
    .live-match .mc-state{color:#2f6b3a;font-size:12px;margin:0;order:2}
    .live-match .mc-basis{order:3;border-top:1px solid #e4e7eb;padding-top:4px}
    .live-match .mc-toggle{border:0;background:none;padding:2px 0;color:#1f5fbf;font-size:13px;text-decoration:underline}
    .live-match .mc-toggle::before{content:'▸ ' attr(data-label)}
    .live-match .mc-toggle[aria-expanded="true"]::before{content:'▾ ' attr(data-label)}
    .live-match .mc-toggle:hover{background:none;color:#174a96}
    .live-match .mc-basis-body{overflow:hidden}
    .live-match .mc-basis-body[data-collapsed]{height:0}
    .live-match .mc-rules{margin:4px 0;color:#1f2933}
    .live-match .mc-quote{color:#3d4a5a;font-size:12px;border-left:3px solid #c9d3df;padding-left:6px;margin:4px 0}
    .live-match .mc-rule-text{margin-top:6px;font-size:11px;color:#52606d}
    .live-match .mc-rule-text p{margin:2px 0}
    .live-match .mc-card dl{order:4;margin:0;display:grid;grid-template-columns:6em 1fr;gap:3px 8px}
    .live-match .mc-card dt{color:#52606d}
    .live-match .mc-card dd{margin:0;color:#1f2933}
    .live-match .mc-thin{margin:0;order:1;color:#1f2933}
    .live-match .mc-card button:not(.mc-toggle),.live-match .mc-dialog button{color:#1f2933;background:#fff;border:1px solid #9aa5b1;
      border-radius:8px;padding:5px 12px;font-size:13px;opacity:1}
    .live-match .mc-card button:not(.mc-toggle):hover,.live-match .mc-dialog button:hover{background:#f0f4f8}
    .live-match .mc-card button.mc-primary:not(.mc-toggle){order:-1;color:#fff;background:#1f5fbf;border-color:#1f5fbf;font-weight:600}
    .live-match .mc-card button.mc-primary:not(.mc-toggle):hover{background:#174a96}
    .live-match .mc-card button:not(.mc-toggle):disabled{color:#3e4c59;background:#e4e7eb;border-color:#cbd2d9;cursor:default}
    .live-match .mc-dialog{position:fixed;inset:0;background:rgba(10,16,32,.45);display:flex;align-items:center;justify-content:center;z-index:50}
    .live-match .mc-dialog>div{background:#fff;color:#1f2933;border-radius:10px;padding:14px 16px;max-width:380px}`;
  document.head.append(style);

  const send = (action, extra) => parent.postMessage({tangle: {
    kind: 'match_task', action,
    ...(snapshot?.task_id ? {task_id: snapshot.task_id} : {}),
    ...(extra || {}),
  }}, location.origin);

  function mountWrap() {
    const box = document.querySelector('[data-match-task]');
    if (!box) return null;
    if (!wrap || !wrap.isConnected) {
      wrap = node('div', null, {class: 'mc-cards', 'data-match-cards': ''});
      box.append(wrap);
    }
    return wrap;
  }

  function closeDialog() { dialog?.remove(); dialog = null; }

  function confirmInvite(card) {
    closeDialog();
    const taskId = snapshot?.task_id;
    dialog = node('div', null, {class: 'mc-dialog', 'data-invite-confirm': card.target, role: 'dialog', 'aria-modal': 'true'});
    const inner = node('div');
    inner.append(node('p', T.confirm(card.name)));
    const row = node('div', null, {class: 'mc-actions'});
    const ok = node('button', T.ok, {type: 'button', 'data-invite-ok': ''});
    const cancel = node('button', T.cancel, {type: 'button', 'data-invite-cancel': ''});
    ok.onclick = () => {
      closeDialog();
      if (snapshot?.task_id !== taskId) return;
      send('invite', {target: card.target, confirmed: true});
    };
    cancel.onclick = closeDialog;
    row.append(ok, cancel);
    inner.append(row);
    dialog.append(inner);
    document.body.append(dialog);
    ok.focus();
  }

  function stateLine(st) {
    const out = [];
    for (const op of OPS) {
      const v = st?.[op];
      if (op === 'supplement') { if (typeof v === 'string') out.push(T.state.supplement[v] || T.state.noted); else if (v) out.push(T.state.asked); }
      else if (v) out.push(T.state[op]);
    }
    if (st?.invite && T.state.invite[st.invite]) out.push(T.state.invite[st.invite]);
    return out.join('・');
  }

  // ── #231 為何推薦拆三層 ──
  // 第一層：一句白話結論（≤ 60 字）。「為何推薦」本身已是短白話（沒有規則原文）就直接用；
  //   否則取「互補性」→「互惠價值」→「建議合作」第一句（LLM／程式寫的白話）。
  // 第二層（「看依據」，預設收起）：規則名稱＋原文引用（[data-why-quotes]）。
  // 第三層：第二層底部的「規則說明」小字＝「為何推薦」全文（含規則原文）。
  // 伺服器各語言的「不足」（app/matching/i18n.py insufficient）＋本表各語言的顯示字。
  const INSUFFICIENT = new Set(['不足', 'Insufficient', '根拠が足りません', '근거 부족',
    ...Object.values(MATCH_I18N).map(t => t.insufficient)]);
  const isThin = v => v == null || INSUFFICIENT.has(String(v).trim()) || !String(v).trim();
  const THIN_FIELDS = ['為何推薦', '互補性', '互惠價值', '建議合作'];
  const CONCLUSION_FROM = ['互補性', '互惠價值', '建議合作'];
  const MAX_CONCLUSION = 60;
  // 程式組的「為何推薦」會帶規則原文（app/matching/i18n.py why.rule）。
  const RULE_TEXT = /規則原文|rule text|ルールの原文|규칙 원문/i;
  const RULE_NAME = /(?:規則|ルール|규칙 ?|rule )[「"]([^」"]+)[」"]/gi;
  const firstSentence = t => {
    const m = String(t).trim().match(/^[\s\S]*?(?:[。！？!?；;]|\.(?=\s|$))/);
    return (m ? m[0] : String(t)).trim();
  };
  const cap = t => (Array.from(t).length > MAX_CONCLUSION ? Array.from(t).slice(0, MAX_CONCLUSION - 1).join('') + '…' : t);
  function whyLayers(card) {
    const f = card.fields || {};
    const why = clean(f['為何推薦']);
    const plainWhy = !isThin(why) && !RULE_TEXT.test(why) && Array.from(why).length <= MAX_CONCLUSION;
    if (plainWhy) return {conclusion: why, whyIsConclusion: true, ruleNames: [], ruleText: ''};
    const src = CONCLUSION_FROM.map(k => f[k]).find(v => !isThin(v));
    const conclusion = cap(clean(src != null ? firstSentence(src) : T.whyFallback));
    const ruleNames = isThin(why) ? [] : [...new Set([...why.matchAll(RULE_NAME)].map(m => m[1].trim()))];
    return {conclusion, whyIsConclusion: false, ruleNames, ruleText: isThin(why) ? '' : why};
  }

  function actionButton(op, card) {
    const b = node('button', T.ops[op], {type: 'button', 'data-card-op': op});
    b.onclick = () => send('card_action', {op, target: card.target});
    return b;
  }

  // 全「不足」的卡：一句說明＋「請對方補資料」（沿用既有的補資料動作 card_action op=supplement）。
  function renderThinCard(card, st) {
    const el = node('article', null, {class: 'mc-card', 'data-match-card': card.target, 'data-card-thin': ''});
    el.append(node('h4', `${card.rank}. ${card.name}`));
    el.append(node('p', T.thin, {class: 'mc-thin', 'data-thin-note': ''}));
    const actions = node('div', null, {class: 'mc-actions'});
    const ask = node('button', T.askInfo, {type: 'button', 'data-card-op': 'supplement'});
    ask.onclick = () => send('card_action', {op: 'supplement', target: card.target});
    actions.append(ask);
    el.append(actions);
    const line = stateLine(st);
    if (line) el.append(node('p', line, {class: 'mc-state', 'data-card-state': ''}));
    return el;
  }

  function renderCard(card, st) {
    const fields = card.fields || {};
    if (THIN_FIELDS.every(k => isThin(fields[k]))) return renderThinCard(card, st);
    const el = node('article', null, {class: 'mc-card', 'data-match-card': card.target});
    el.append(node('h4', `${card.rank}. ${card.name}`));

    // 第一層：結論
    const layers = whyLayers(card);
    const lead = node('div', null, {class: 'mc-lead'});
    lead.append(node('span', T.fields['為何推薦'], {class: 'mc-label'}));
    const conclusion = node('p', layers.conclusion, {class: 'mc-conclusion', 'data-why-conclusion': ''});
    if (layers.whyIsConclusion) conclusion.setAttribute('data-field', '為何推薦');
    lead.append(conclusion);
    el.append(lead);

    // 第二、三層：看依據
    const quotes = card['原文段落'] || [];
    if (quotes.length || layers.ruleNames.length || layers.ruleText) {
      const openKey = `${snapshot?.task_id}|${card.target}`;
      const basis = node('div', null, {class: 'mc-basis', 'data-why-basis': ''});
      const bodyId = `mc-basis-${String(card.target).replace(/[^\w-]/g, '_')}`;
      // 鈕的字由 CSS 依 data-label 畫出（不寫進 DOM 文字），卡片的閱讀文字維持原樣。
      const toggle = node('button', null, {type: 'button', class: 'mc-toggle', 'data-why-toggle': '', 'aria-controls': bodyId});
      const body = node('div', null, {class: 'mc-basis-body', id: bodyId});
      const setOpen = open => {
        toggle.setAttribute('aria-expanded', String(open));
        toggle.setAttribute('data-label', open ? T.basis.hide : T.basis.show);
        body.toggleAttribute('data-collapsed', !open);
        body.toggleAttribute('inert', !open);
        body.setAttribute('aria-hidden', String(!open));
        if (open) opened.add(openKey); else opened.delete(openKey);
      };
      toggle.onclick = () => setOpen(toggle.getAttribute('aria-expanded') !== 'true');
      if (layers.ruleNames.length) body.append(node('p', T.rules(layers.ruleNames.join(T.sep)), {class: 'mc-rules', 'data-why-rules': ''}));
      if (quotes.length) {
        body.append(node('span', T.quoteLabel, {class: 'mc-label'}));
        const box = node('div', null, {'data-why-quotes': ''});
        for (const qt of quotes) box.append(node('p', T.quote(qt['計畫'], qt['段落'], qt['原文']), {class: 'mc-quote'}));
        body.append(box);
      }
      if (layers.ruleText) {
        const small = node('div', null, {class: 'mc-rule-text', 'data-why-rule': ''});
        small.append(node('span', T.ruleText, {class: 'mc-label'}), node('p', layers.ruleText, {'data-field': '為何推薦'}));
        body.append(small);
      }
      setOpen(opened.has(openKey));
      basis.append(toggle, body);
      el.append(basis);
    }

    // 其他欄位
    const dl = node('dl');
    for (const [k, v] of Object.entries(fields)) {
      if (k === '為何推薦') continue;
      dl.append(node('dt', T.fields[k] || k), node('dd', valueText(v), {'data-field': k}));
    }
    const ne = Object.keys(card['未評估'] || {});
    if (ne.length) dl.append(node('dt', T.notEvaluated),
      node('dd', ne.map(n => T.pair(T.dims[n] || n, T.notEvaluated)).join(T.sep), {'data-not-evaluated': ''}));
    if (dl.childNodes.length) el.append(dl);

    // 按鈕列（視覺上在結論下方）：寄站內邀請是唯一實心主要按鈕，其餘次要。
    const actions = node('div', null, {class: 'mc-actions'});
    for (const op of OPS) actions.append(actionButton(op, card));
    const inv = node('button', st?.invite === 'sent' ? T.invited : T.invite, {type: 'button', class: 'mc-primary', 'data-card-invite': ''});
    inv.disabled = st?.invite === 'sent';
    inv.onclick = () => confirmInvite(card);
    actions.append(inv);
    el.append(actions);
    const line = stateLine(st);
    if (line) el.append(node('p', line, {class: 'mc-state', 'data-card-state': ''}));
    return el;
  }

  function render() {
    const w = mountWrap();
    if (!w) return;
    const s = snapshot || {};
    const cards = s.status === 'done' ? (s.cards || []) : [];
    lang = normLang(s.lang) || cookieLang() || 'zh';
    T = MATCH_I18N[lang];
    const next = JSON.stringify([s.task_id, cards, s.card_state || {}, lang]);
    if (next === key) return;
    key = next;
    w.replaceChildren();
    if (!cards.length) { w.hidden = true; return; }
    w.hidden = false;
    w.append(node('h3', T.title));
    w.append(node('p', T.note, {class: 'mt-note'}));
    for (const c of cards) w.append(renderCard(c, (s.card_state || {})[c.target]));
  }

  function accept(next) {
    if (!next || typeof next !== 'object' || !next.task_id) return;
    if (snapshot?.task_id !== next.task_id) closeDialog();
    snapshot = next;
    render();
  }

  const onCall = e => {
    const d = e.detail || {};
    if (d.name !== 'tangle_workspace' || d.args?.mode !== 'match' || !d.args?.matchTask) return;
    accept(d.args.matchTask);
  };
  try { parent.addEventListener('chainlit-call-fn', onCall); } catch (_) { /* 非同源時只靠 message */ }
  window.addEventListener('pagehide', () => { try { parent.removeEventListener('chainlit-call-fn', onCall); } catch (_) {} });
  window.addEventListener('message', e => {
    if (e.origin !== location.origin || e.source !== parent) return;
    if (e.data?.type === 'tangle-match-task') accept(e.data.snapshot);
  });
  // match-task.js 先建好 [data-match-task]；若順序不同，等它出現再掛。
  if (!mountWrap()) {
    const mo = new MutationObserver(() => { if (mountWrap()) { mo.disconnect(); render(); } });
    mo.observe(document.body, {childList: true, subtree: true});
  }
})();
