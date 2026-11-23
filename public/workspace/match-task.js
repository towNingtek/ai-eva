// #203 真實媒合任務工作區（只在 mode=match&v=live-match 時接手；示範與雲林的媒合維持原樣）。
// 狀態一律由伺服器決定：載入時送 get，之後跟著 Eva 推來的 tangle_workspace(matchTask) 更新。
// 同一對話返回只會接回原任務；只有「開始新媒合」會建新任務。
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get('mode') !== 'match' || q.get('v') !== 'live-match') return;
  const $id = id => document.getElementById(id);
  const mount = $id('deskMount');
  if (!mount) return;
  document.body.classList.add('workspace-open', 'live-match');
  const foot = document.querySelector('.desk-foot');
  if (foot) foot.hidden = true;
  const node = (tag, text, attrs) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    return el;
  };
  const button = (text, click, attrs) => {
    const b = node('button', text, attrs);
    b.type = 'button';
    b.onclick = click;
    return b;
  };
  const style = node('style');
  style.textContent = `
    .live-match .mt-box{padding:12px 14px;display:flex;flex-direction:column;gap:10px;font-size:14px}
    .live-match .mt-box fieldset{border:1px solid #d8dee6;border-radius:8px;padding:8px 10px}
    .live-match .mt-box label{display:block;margin:3px 0}
    .live-match .mt-box table{border-collapse:collapse;width:100%}
    .live-match .mt-box th,.live-match .mt-box td{border-bottom:1px solid #e5e9ef;padding:4px 6px;text-align:left;vertical-align:top}
    .live-match .mt-box tr[data-shown="1"] td:first-child{font-weight:600}
    .live-match .mt-galaxy iframe{width:100%;height:540px;border:0;border-radius:10px;background:#0b1020}
    .live-match .mt-error{color:#a33}
    .live-match .mt-note{color:#5f6b7a;font-size:12px}`;
  document.head.append(style);
  const box = node('div', null, {class: 'mt-box', 'data-match-task': ''});
  const status = node('p', null, {role: 'status'});
  const controls = node('div');
  const compare = node('div', null, {'data-match-compare': ''});
  const galaxy = node('div', null, {class: 'mt-galaxy'});
  const details = node('div');
  box.append(status, controls, compare, galaxy, details);
  mount.replaceChildren(box);
  const title = $id('deskTitle');
  const setTitle = t => { if (title) title.textContent = t; };
  setTitle('專案媒合工作區');

  let snapshot = null, pending = null, controlsKey = null, frame = null, frameKey = null, shown = [];
  let polling = null, closed = false;
  const send = (action, extra) => parent.postMessage({tangle: {
    kind: 'match_task', action,
    ...(snapshot?.task_id ? {task_id: snapshot.task_id} : {}),
    ...(extra || {})
  }}, location.origin);
  function submit(action, extra) {
    if (pending) return;
    pending = setTimeout(() => {
      pending = null; controlsKey = null; render();
      status.textContent = '尚未收到回應，正在重新確認目前進度…';
      if (!closed) send('get');
    }, 12000);
    controlsKey = null;
    render();
    send(action, extra);
  }
  const nameOf = pid => (snapshot?.projects || []).find(p => p.uuid === pid)?.name
    || (snapshot?.result?.projects || []).find(p => p.pid === pid)?.name || pid;
  const LABELS = {loading: '載入專案清單中…', select: '請選擇 A，以及 2–4 個要比較的對象。',
    running: '正在判斷各案的需要／能提供…', done: '媒合判斷完成（不推薦、不自動聯絡）', error: '媒合未完成'};

  function renderSelect(s) {
    const options = (Array.isArray(s.projects) ? s.projects : []).filter(p => p?.uuid && p?.name);
    const min = s.min_targets || 2, max = s.max_targets || 4;
    const label = node('label', '專案 A ');
    const a = node('select', null, {'aria-label': '專案 A', 'data-match-a': ''});
    for (const p of options) { const o = node('option', p.name); o.value = p.uuid; a.append(o); }
    if (s.a) a.value = s.a;
    label.append(a);
    const set = node('fieldset');
    set.append(node('legend', `比較對象（${min}–${max} 個）`));
    const checks = [];
    const start = button('開始媒合 →', () => {
      const targets = checks.filter(c => c.checked).map(c => c.value);
      submit('select', {a: a.value, targets});
    }, {'data-match-start': ''});
    const sync = () => {
      let n = 0;
      for (const c of checks) {
        if (c.value === a.value) c.checked = false;
        c.disabled = !!pending || c.value === a.value;
        if (c.checked) n++;
      }
      for (const c of checks) if (!c.checked && n >= max) c.disabled = true;
      start.disabled = !!pending || n < min || n > max;
      hint.textContent = `已選 ${n} 個`;
    };
    for (const p of options) {
      const row = node('label');
      const c = node('input', null, {type: 'checkbox', 'data-match-target': p.uuid});
      c.value = p.uuid;
      c.checked = (s.targets || []).includes(p.uuid);
      c.onchange = sync;
      checks.push(c);
      row.append(c, document.createTextNode(' ' + p.name));
      set.append(row);
    }
    const hint = node('span', '', {class: 'mt-note'});
    a.onchange = sync;
    a.disabled = !!pending;
    controls.append(label, set, start, hint);
    sync();
  }

  function renderCompare(res) {
    compare.replaceChildren();
    const pairs = Array.isArray(res?.pairs) ? res.pairs : [];
    if (!pairs.length) return;
    compare.append(node('h3', `${pairs.length} 案比較（A：${nameOf(res.a)}）`));
    const table = node('table'), head = node('tr'), body = node('tbody');
    for (const h of ['對象', '狀態', '互補候選', '共同尋找第三方', '可聯合或交流', '畫面']) head.append(node('th', h, {scope: 'col'}));
    const thead = node('thead'); thead.append(head); table.append(thead, body);
    for (const p of pairs) {
      const on = shown.includes(p.pb);
      const tr = node('tr', null, {'data-match-pair': p.pair, 'data-shown': on ? '1' : '0'});
      const c = p.counts || {};
      for (const v of [nameOf(p.pb), p.status_text || p.status, c.complement ?? 0, c.third ?? 0, c.peer ?? 0]) tr.append(node('td', String(v)));
      const td = node('td');
      td.append(button(on ? '星圖中' : '放進星圖', () => focusTarget(p.pb), {'data-match-show': p.pb}));
      td.append(document.createTextNode(' '));
      td.append(button('請 Eva 說明', () => send('explain', {pa: p.pa, pb: p.pb, kind: 'pair'}), {'data-match-explain': p.pair}));
      tr.append(td);
      body.append(tr);
    }
    compare.append(table);
    if (pairs.length > 3) compare.append(node('p', '星圖最多同時畫 A 與 3 個對象；用「放進星圖」切換。', {class: 'mt-note'}));
  }

  function focusTarget(pid) {
    const res = snapshot?.result;
    if (!res) return;
    const targets = (res.projects || []).slice(1).map(p => p.pid);
    if (shown.includes(pid)) return;
    shown = [pid, ...shown.filter(x => x !== pid)].slice(0, 3);
    shown = targets.filter(t => shown.includes(t));
    frameKey = undefined;
    render();
  }

  function postStatus() {
    const res = snapshot?.result;
    if (!frame?.contentWindow || !res) return;
    const ids = [res.a, ...shown];
    for (const p of res.pairs || []) {
      if (!ids.includes(p.pa) || !ids.includes(p.pb)) continue;
      frame.contentWindow.postMessage({type: 'mf-status', pair: p.pair, status: p.status}, location.origin);
      if (ids.length === 2) frame.contentWindow.postMessage({type: 'mf-status', status: p.status}, location.origin);
    }
  }

  function renderGalaxy(s) {
    const res = s.status === 'done' ? s.result : null;
    const targets = res ? (res.projects || []).slice(1).map(p => p.pid) : [];
    if (res && !shown.length) shown = targets.slice(0, 3);
    window.__matchGalaxy = res;
    const key = res ? `${s.task_id}:${[res.a, ...shown].join(',')}` : null;
    if (frameKey === key) return;
    frameKey = key;
    galaxy.replaceChildren();
    frame = null;
    if (!key) return;
    frame = node('iframe', null, {title: '本次媒合星系', 'data-match-galaxy': ''});
    frame.addEventListener('load', postStatus);
    frame.src = '/public/tangle/tangle-match.html?liveMatch=1&v=live-match&t=' + encodeURIComponent(s.task_id)
      + '&ps=' + [res.a, ...shown].map(encodeURIComponent).join(',');
    galaxy.append(frame);
    galaxy.append(node('p', res.note || '', {class: 'mt-note'}));
  }

  function render() {
    const s = snapshot || {};
    const phase = s.status || 'loading';
    const text = pending ? '已送出，等待工作區更新…' : (LABELS[phase] || LABELS.loading);
    if (status.textContent !== text) status.textContent = text;
    setTitle(s.a ? `專案媒合 / ${nameOf(s.a)}` : '專案媒合工作區');
    const key = JSON.stringify([s.task_id, phase, s.projects, s.error, !!pending]);
    if (controlsKey !== key) {
      controlsKey = key;
      controls.replaceChildren();
      if (s.error) controls.append(node('p', s.error, {class: 'mt-error', role: 'alert'}));
      if (phase === 'select') renderSelect(s);
      if (phase === 'loading' || phase === 'running') {
        const refresh = button('更新進度', () => send('get'));
        refresh.disabled = !s.task_id;
        controls.append(refresh);
      }
      if (phase === 'done' || phase === 'error') {
        const again = button('開始新媒合', () => { shown = []; submit('new'); }, {'data-match-new': ''});
        again.disabled = !!pending;
        controls.append(again);
      }
    }
    renderCompare(phase === 'done' ? s.result : null);
    renderGalaxy(s);
    details.replaceChildren();
    if (phase === 'running') {
      const done = (s.progress || []).filter(p => p?.step === 'fetch').map(p => p.name);
      if (done.length) details.append(node('p', `已讀取：${done.join('、')}`));
    }
  }

  function accept(next) {
    if (!next || typeof next !== 'object' || !next.task_id) return;
    if (snapshot?.task_id !== next.task_id || snapshot?.status !== next.status || next.error) {
      clearTimeout(pending);
      pending = null;
    }
    if (snapshot?.task_id !== next.task_id) { shown = []; frameKey = undefined; }
    snapshot = next;
    render();
    if ((next.status === 'loading' || next.status === 'running') && !closed) {
      if (!polling) polling = setInterval(() => send('get'), 3000);
    } else { clearInterval(polling); polling = null; }
  }

  // Eva → 工作區：overlay 只轉發法規的 update，但每次都會在 parent 觸發 chainlit-call-fn，這裡直接讀。
  const onCall = e => {
    const d = e.detail || {};
    if (d.name !== 'tangle_workspace' || d.args?.mode !== 'match' || !d.args?.matchTask) return;
    closed = false;
    accept(d.args.matchTask);
  };
  try { parent.addEventListener('chainlit-call-fn', onCall); } catch (_) { /* 非同源時只靠 message */ }
  window.addEventListener('pagehide', () => {
    clearInterval(polling); polling = null;
    try { parent.removeEventListener('chainlit-call-fn', onCall); } catch (_) {}
  });

  window.addEventListener('message', e => {
    if (e.origin !== location.origin) return;
    if (e.source === parent) {
      if (e.data?.type === 'tangle-ws-closed') { closed = true; clearInterval(polling); polling = null; }
      if (e.data?.type === 'tangle-match-task') accept(e.data.snapshot);
      return;
    }
    // 星圖點擊 → 請 Eva 說明這次結果（不重判）。
    if (!frame || e.source !== frame.contentWindow) return;
    const m = e.data || {};
    if (m.type !== 'tangle-relation' || !snapshot?.task_id || snapshot.status !== 'done') return;
    const ids = [snapshot.result?.a, ...shown];
    const bySubject = typeof m.subject === 'number' ? ids[m.subject - 1] : null;
    const ev = {code: m.code, kind: m.kind, subject: bySubject || null, tag: m.tag};
    if (m.pa && m.pb) { ev.pa = m.pa; ev.pb = m.pb; }
    const who = m.who || bySubject;
    if (who) ev.who = who;
    send('explain', ev);
  });

  render();
  send('get');
})();
