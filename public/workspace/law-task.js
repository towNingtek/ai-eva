// Real law task UI. The regular lab bridge remains in charge of demo and matching modes.
(() => {
  const q = new URLSearchParams(location.search);
  if (q.get('mode') !== 'law' || q.get('liveLaw') !== '1') return;
  document.body.classList.add('workspace-open', 'live-law');
  const node = (tag, text) => {
    const el = document.createElement(tag);
    if (text != null) el.textContent = text;
    return el;
  };
  const status = node('p');
  status.setAttribute('role', 'status');
  const controls = node('div');
  const details = node('div');
  const galaxy = node('div');
  document.querySelector('.desk-foot').hidden = true;
  $('deskTitle').textContent = '法規檢核工作區';
  $('deskMount').append(status, controls, galaxy, details);
  let snapshot, phase, pending, frame, frameKey, controlsKey;
  const send = (action, uuid) => parent.postMessage({tangle: {
    kind: 'law_task', action,
    ...(snapshot?.task_id ? {task_id:snapshot.task_id} : {}),
    ...(uuid ? {uuid} : {})
  }}, location.origin);
  const postGalaxy = () => frame?.contentWindow?.postMessage({type: 'tangle-law-task', snapshot}, location.origin);
  const button = (text, click) => {
    const b = node('button', text);
    b.type = 'button';
    b.onclick = click;
    return b;
  };
  function submit(action, uuid) {
    if (pending) return;
    pending = setTimeout(() => {
      pending = null;
      controlsKey = null;
      render();
      status.textContent = '尚未收到回應，正在重新確認目前進度…';
      if (!closed) send('get');
    }, 12000);
    render();
    send(action, uuid);
  }
  function render() {
    const s = snapshot || {}, project = s.project;
    const labels = {loading:'載入專案清單中…', selecting:'請選擇此次要檢核的專案。', running:'正在進行法規檢核…', completed:'法規檢核完成', failed:'法規檢核未完成'};
    const text = pending ? '已送出，等待工作區更新…' : labels[phase] || labels.loading;
    if (status.textContent !== text) status.textContent = text;
    $('deskTitle').textContent = project?.name ? `法規檢核 / ${project.name}` : '法規檢核工作區';
    const key = JSON.stringify([s.task_id, phase, s.projects, !!pending]);
    if (controlsKey !== key) {
      controlsKey = key;
      controls.replaceChildren();
      if (phase === 'selecting') {
        const options = (Array.isArray(s.projects) ? s.projects : []).filter(p => p?.uuid && p?.name);
        if (!options.length) controls.append(node('p', '目前沒有可供檢核的專案。'));
        else {
          const label = node('label', '分析專案 '), select = node('select');
          label.append(select);
          for (const p of options) {
            const option = node('option', p.name);
            option.value = p.uuid;
            select.append(option);
          }
          const start = button('開始法規檢核 →', () => submit('select', select.value));
          select.disabled = start.disabled = !!pending;
          controls.append(label, start);
        }
      }
      if (phase === 'completed' || phase === 'failed') {
        const again = button('開始新的法規檢核', () => submit('new'));
        again.disabled = !!pending;
        controls.append(again);
        if (phase === 'completed') controls.append(button('回到聊天下載報告 ↗', () => parent.postMessage({type:'tangle-ws-close'}, location.origin)));
      }
      if (phase === 'loading' || phase === 'running') {
        const refresh = button('更新進度', () => send('get'));
        refresh.disabled = !s.task_id;
        controls.append(refresh);
      }
    }
    const galaxyKey = project && ['running', 'completed', 'failed'].includes(phase) ? `${s.task_id}:${project.uuid}` : null;
    if (frameKey !== galaxyKey) {
      frameKey = galaxyKey;
      galaxy.replaceChildren();
      frame = null;
      if (galaxyKey) {
        frame = node('iframe');
        frame.title = '本次法規檢核星系';
        frame.addEventListener('load', postGalaxy);
        frame.src = '/public/tangle/tangle-law.html?liveLaw=1&b=law-task-1';
        galaxy.append(frame);
      }
    }
    postGalaxy();
    details.replaceChildren();
    const progress = Array.isArray(s.progress) ? s.progress : [];
    if (progress.length) {
      details.append(node('h3', '各法領域進度'));
      const table = node('table'), head = node('thead'), header = node('tr'), body = node('tbody');
      for (const name of ['法領域', '檢核數', '命中數', '耗時（秒）']) {
        const th = node('th', name);
        th.scope = 'col';
        header.append(th);
      }
      head.append(header);
      for (const r of progress) {
        if (!r?.domain) continue;
        const tr = node('tr');
        // Elapsed arrives as raw float seconds (e.g. 29.02004861831665); show whole seconds.
        const secs = Number.isFinite(r.elapsed) ? Math.round(r.elapsed) : r.elapsed;
        for (const value of [r.domain, r.total, r.hit, secs]) tr.append(node('td', value ?? '—'));
        body.append(tr);
      }
      table.append(head, body);
      details.append(table);
    }
    if (phase === 'completed') {
      const result = s.result || {}, summary = result.summary ?? s.summary;
      const counts = [['違規風險',result.violations],['提醒',result.reminders],['資料缺口',result.gaps],['已檢核',result.evaluated]]
        .filter(([, n]) => typeof n === 'number').map(([label, n]) => `${label} ${n}`);
      if (counts.length) details.append(node('p', counts.join('・')));
      if (typeof summary === 'string' && summary) details.append(node('p', summary));
      const name = result.attachment?.name ?? s.report?.name;
      if (name) details.append(node('p', `報告：${name}（請回原對話下載）`));
    }
    if (phase === 'failed') details.append(node('p', s.error || '請重新開始檢核，或回到原對話查看。'));
  }
  let polling, closed = false;
  const stopPolling = () => { clearInterval(polling); polling = null; };
  window.addEventListener('pagehide', stopPolling);
  // A satellite was clicked in the finished galaxy → ask Eva to explain that domain of THIS task (no re-judging).
  window.addEventListener('message', e => {
    if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow) return;
    if (e.data?.type !== 'tangle-law-domain' || typeof e.data.domain !== 'string' || !snapshot?.task_id) return;
    parent.postMessage({tangle: {kind: 'law_task', action: 'domain', task_id: snapshot.task_id, domain: e.data.domain}}, location.origin);
  });
  window.addEventListener('message', e => {
    if (e.origin !== location.origin || e.source !== parent) return;
    if (e.data?.type === 'tangle-ws-closed') { closed = true; stopPolling(); return; }
    if (e.data?.type !== 'tangle-law-task') return;
    closed = !!e.data.closed;
    const next = e.data.snapshot;
    if (!next || typeof next !== 'object') return;
    const newPhase = ({select:'selecting', done:'completed', error:'failed'})[next.status] || next.status;
    if (snapshot?.task_id !== next.task_id || phase !== newPhase) {
      clearTimeout(pending);
      pending = null;
    }
    snapshot = next;
    phase = newPhase;
    render();
    if (phase === 'loading' || phase === 'running') {
      if (!polling && !e.data.closed) polling = setInterval(() => send('get'), 3000);
    } else stopPolling();
  });
  render();
})();
