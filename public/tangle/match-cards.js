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
  const OPS = [['favorite', '收藏'], ['skip', '略過'], ['supplement', '補資料']];
  const STATE_TEXT = {
    favorite: '已收藏', skip: '已略過',
    invite: {confirm: '等待確認寄出', sent: '已寄出站內邀請', error: '邀請沒有寄出'},
    supplement: {ok: '補充已寫回計畫理念', declined: '補充只留在紀錄', not_manageable: '補充已記下（不可寫回）'},
  };

  let snapshot = null, wrap = null, dialog = null, key = null;

  const style = document.createElement('style');
  style.textContent = `
    .live-match .mc-cards{display:flex;flex-direction:column;gap:10px}
    .live-match .mc-card{border:1px solid #d8dee6;border-radius:10px;padding:10px 12px;background:#fff}
    .live-match .mc-card h4{margin:0 0 6px;font-size:15px}
    .live-match .mc-card dl{margin:0;display:grid;grid-template-columns:6em 1fr;gap:3px 8px}
    .live-match .mc-card dt{color:#5f6b7a}
    .live-match .mc-card dd{margin:0}
    .live-match .mc-quote{color:#3d4a5a;font-size:12px;border-left:3px solid #c9d3df;padding-left:6px;margin:4px 0}
    .live-match .mc-actions{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
    .live-match .mc-state{color:#2f6b3a;font-size:12px}
    .live-match .mc-dialog{position:fixed;inset:0;background:rgba(10,16,32,.45);display:flex;align-items:center;justify-content:center;z-index:50}
    .live-match .mc-dialog>div{background:#fff;border-radius:10px;padding:14px 16px;max-width:380px}`;
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
    inner.append(node('p', `確定要寄站內邀請給「${card.name}」嗎？寄出後對方會收到通知。`));
    const row = node('div', null, {class: 'mc-actions'});
    const ok = node('button', '確定寄出', {type: 'button', 'data-invite-ok': ''});
    const cancel = node('button', '取消', {type: 'button', 'data-invite-cancel': ''});
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
    for (const [op] of OPS) {
      const v = st?.[op];
      if (op === 'supplement') { if (typeof v === 'string') out.push(STATE_TEXT.supplement[v] || '補充已記下'); else if (v) out.push('已請 Eva 問補資料'); }
      else if (v) out.push(STATE_TEXT[op]);
    }
    if (st?.invite && STATE_TEXT.invite[st.invite]) out.push(STATE_TEXT.invite[st.invite]);
    return out.join('・');
  }

  function renderCard(card, st) {
    const el = node('article', null, {class: 'mc-card', 'data-match-card': card.target});
    el.append(node('h4', `${card.rank}. ${card.name}`));
    const dl = node('dl');
    for (const [k, v] of Object.entries(card.fields || {})) {
      dl.append(node('dt', k), node('dd', v, {'data-field': k}));
      if (k === '為何推薦') {
        const dd = node('dd', null, {'data-why-quotes': ''});
        for (const qt of card['原文段落'] || []) {
          dd.append(node('p', `${qt['計畫']}・第 ${qt['段落']} 段：「${qt['原文']}」`, {class: 'mc-quote'}));
        }
        if (dd.childNodes.length) dl.append(node('dt', '原文'), dd);
      }
    }
    const ne = Object.keys(card['未評估'] || {});
    if (ne.length) dl.append(node('dt', '未評估'), node('dd', ne.map(n => `${n}：未評估`).join('、'), {'data-not-evaluated': ''}));
    el.append(dl);
    const actions = node('div', null, {class: 'mc-actions'});
    for (const [op, label] of OPS) {
      const b = node('button', label, {type: 'button', 'data-card-op': op});
      b.onclick = () => send('card_action', {op, target: card.target});
      actions.append(b);
    }
    const inv = node('button', st?.invite === 'sent' ? '已寄出邀請' : '寄站內邀請', {type: 'button', 'data-card-invite': ''});
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
    const next = JSON.stringify([s.task_id, cards, s.card_state || {}]);
    if (next === key) return;
    key = next;
    w.replaceChildren();
    if (!cards.length) { w.hidden = true; return; }
    w.hidden = false;
    w.append(node('h3', '媒合建議卡'));
    w.append(node('p', '依這次判斷排出的建議；要不要聯絡、怎麼開始由你決定。寄站內邀請前會再請你確認。', {class: 'mt-note'}));
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
