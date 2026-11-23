// #203 真實媒合任務工作區（只在 mode=match&v=live-match 時接手；示範與雲林的媒合維持原樣）。
// 狀態一律由伺服器決定：載入時送 get，之後跟著 Eva 推來的 tangle_workspace(matchTask) 更新。
// 同一對話返回只會接回原任務；只有「開始新媒合」會建新任務。
// #226 介面文字依使用者語言：任務狀態帶的 lang 優先，沒有時讀 eva_lang cookie，都沒有用 zh。
// 專案名稱、伺服器給的原文不翻；zh 的文字與改版前相同。
(() => {
  const MATCH_I18N = {
    zh: {
      match: '專案媒合', workspace: '工作區', desk: '策略工作區', chat: '對話 ⇄', collapse: '收合 ↗',
      labels: {loading: '載入專案清單中…', select: '請選擇 A，以及 2–4 個要比較的對象。',
        running: '正在判斷各案的需要／能提供…', done: '媒合判斷完成（不推薦、不自動聯絡）', error: '媒合未完成'},
      noReply: '尚未收到回應，正在重新確認目前進度…', pending: '已送出，等待工作區更新…',
      search: '搜尋名稱', searchLabel: '依名稱搜尋對象', projectA: '專案 A', targets: (min, max) => `比較對象（${min}–${max} 個）`, start: '開始媒合 →', picked: n => `已選 ${n} 個`,
      compare: (n, name) => `${n} 案比較（A：${name}）`,
      cols: ['對象', '狀態', '互補候選', '共同尋找第三方', '可聯合或交流', '畫面'],
      inGalaxy: '星圖中', toGalaxy: '放進星圖', askEva: '請 Eva 說明',
      galaxyLimit: '星圖最多同時畫 A 與 3 個對象；用「放進星圖」切換。', galaxyTitle: '本次媒合星系', galaxyFit: '重設',
      galaxyNote: 'B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。',
      refresh: '更新進度', again: '開始新媒合', fetched: list => `已讀取：${list.join('、')}`,
      status: {CLARIFY_FIRST: '先補資料', EXPLORE: '可探索', ELIGIBLE: '可排序・未建議', RECOMMEND: '推薦', EXCLUDED: '不在範圍'},
      errors: {interrupted: '媒合已中斷，請按「開始新媒合」。', listFailed: '讀取專案清單失敗，請按「開始新媒合」再試。',
        notEnough: '媒合需要 A 加上至少 2 個對象，目前可用的專案不夠。',
        noInitiable: '你在這個站還沒有可以發起媒合的專案（只有本站可管理的專案能寄出媒合邀請）。',
        unreadable: '無法讀取其中一個專案，請按「開始新媒合」。', pickA: '請先選擇你的專案 A。',
        targets: '請重新勾選 2–4 個媒合對象。', failed: '媒合失敗，請稍後按「開始新媒合」。'},
    },
    en: {
      match: 'Project matching', workspace: ' workspace', desk: 'Strategy workspace', chat: 'Chat ⇄', collapse: 'Collapse ↗',
      labels: {loading: 'Loading the project list…', select: 'Choose project A and 2–4 projects to compare.',
        running: 'Working out what each project needs / can offer…',
        done: 'Matching complete (no recommendation, no automatic contact)', error: 'Matching not completed'},
      noReply: 'No response yet; checking the current progress again…', pending: 'Sent; waiting for the workspace to update…',
      search: 'Search by name', searchLabel: 'Search projects by name', projectA: 'Project A', targets: (min, max) => `Projects to compare (${min}–${max})`, start: 'Start matching →',
      picked: n => `${n} selected`,
      compare: (n, name) => `Comparing ${n} projects (A: ${name})`,
      cols: ['Project', 'Status', 'Complementary candidates', 'Seek a third party together', 'Can join forces or exchange', 'View'],
      inGalaxy: 'In the galaxy', toGalaxy: 'Show in galaxy', askEva: 'Ask Eva to explain',
      galaxyLimit: 'The galaxy shows A and at most 3 projects at a time; use "Show in galaxy" to switch.',
      galaxyTitle: 'Matching galaxy for this run', galaxyFit: 'Reset view',
      galaxyNote: 'B1–B8 and needs / offers are AI inferences (not confirmed by the owner); evidence is the original plan text. Phase 1 does not recommend or contact anyone automatically.',
      refresh: 'Refresh progress', again: 'Start a new match', fetched: list => `Read: ${list.join(', ')}`,
      status: {CLARIFY_FIRST: 'Add details first', EXPLORE: 'Worth exploring', ELIGIBLE: 'Rankable, not suggested',
        RECOMMEND: 'Recommended', EXCLUDED: 'Out of scope'},
      errors: {interrupted: 'Matching was interrupted. Press "Start a new match".',
        listFailed: 'Could not load the project list. Press "Start a new match" to try again.',
        notEnough: 'Matching needs A plus at least 2 projects, but not enough projects are available.',
        noInitiable: 'You have no project on this site that can start a match (only projects you manage here can send match invitations).',
        unreadable: 'One of the projects cannot be read. Press "Start a new match".', pickA: 'Please choose your project A first.',
        targets: 'Please select 2–4 projects to compare again.', failed: 'Matching failed. Please press "Start a new match" later.'},
    },
    ja: {
      match: 'プロジェクトマッチング', workspace: 'ワークスペース', desk: '戦略ワークスペース', chat: 'チャット ⇄', collapse: '折りたたむ ↗',
      labels: {loading: 'プロジェクト一覧を読み込んでいます…', select: 'プロジェクト A と、比較する相手を 2～4 件選んでください。',
        running: '各プロジェクトの「必要なもの／提供できるもの」を判定しています…',
        done: 'マッチングの判定が完了しました（推薦・自動連絡はしません）', error: 'マッチングは完了していません'},
      noReply: 'まだ応答がありません。現在の進み具合を確認し直しています…', pending: '送信しました。ワークスペースの更新を待っています…',
      search: '名前で検索', searchLabel: '名前で相手を検索', projectA: 'プロジェクト A', targets: (min, max) => `比較する相手（${min}～${max} 件）`, start: 'マッチングを開始 →',
      picked: n => `${n} 件を選択`,
      compare: (n, name) => `${n} 件の比較（A：${name}）`,
      cols: ['相手', 'ステータス', '補完の候補', '一緒に第三者を探す', '連携・交流できる', '表示'],
      inGalaxy: '星図に表示中', toGalaxy: '星図に入れる', askEva: 'Eva に説明してもらう',
      galaxyLimit: '星図には A と最大 3 件までを同時に表示します。「星図に入れる」で切り替えてください。',
      galaxyTitle: '今回のマッチングの星系', galaxyFit: '表示をリセット',
      galaxyNote: 'B1–B8 と「必要／提供できる」は AI の推論です（オーナー未確認）。evidence はプランの理念の原文です。第 1 期は推薦も自動連絡もしません。',
      refresh: '進み具合を更新', again: '新しいマッチングを開始', fetched: list => `読み込み済み：${list.join('、')}`,
      status: {CLARIFY_FIRST: '先に情報を補う', EXPLORE: '検討できる', ELIGIBLE: '順位付けのみ・提案なし', RECOMMEND: 'おすすめ', EXCLUDED: '対象外'},
      errors: {interrupted: 'マッチングが中断されました。「新しいマッチングを開始」を押してください。',
        listFailed: 'プロジェクト一覧を読み込めませんでした。「新しいマッチングを開始」を押してもう一度お試しください。',
        notEnough: 'マッチングには A と 2 件以上の相手が必要ですが、利用できるプロジェクトが足りません。',
        noInitiable: 'このサイトでマッチングを始められるプロジェクトがまだありません（このサイトで管理できるプロジェクトだけが招待を送れます）。',
        unreadable: 'プロジェクトの一つを読み込めません。「新しいマッチングを開始」を押してください。',
        pickA: '先にあなたのプロジェクト A を選んでください。', targets: '比較する相手を 2～4 件選び直してください。',
        failed: 'マッチングに失敗しました。しばらくしてから「新しいマッチングを開始」を押してください。'},
    },
    ko: {
      match: '프로젝트 매칭', workspace: ' 작업 공간', desk: '전략 작업 공간', chat: '대화 ⇄', collapse: '접기 ↗',
      labels: {loading: '프로젝트 목록을 불러오는 중…', select: '프로젝트 A와 비교할 대상 2–4개를 선택하세요.',
        running: '각 프로젝트의 필요／제공 가능 항목을 판단하는 중…', done: '매칭 판단 완료(추천하지 않으며 자동으로 연락하지 않음)',
        error: '매칭이 완료되지 않았습니다'},
      noReply: '아직 응답이 없습니다. 현재 진행 상황을 다시 확인하는 중…', pending: '보냈습니다. 작업 공간 업데이트를 기다리는 중…',
      search: '이름으로 검색', searchLabel: '이름으로 대상 검색', projectA: '프로젝트 A', targets: (min, max) => `비교 대상(${min}–${max}개)`, start: '매칭 시작 →', picked: n => `${n}개 선택됨`,
      compare: (n, name) => `${n}개 비교(A: ${name})`,
      cols: ['대상', '상태', '보완 후보', '함께 제3자 찾기', '연대·교류 가능', '화면'],
      inGalaxy: '성도에 표시 중', toGalaxy: '성도에 넣기', askEva: 'Eva에게 설명 요청',
      galaxyLimit: '성도에는 A와 최대 3개 대상까지 동시에 표시됩니다. "성도에 넣기"로 전환하세요.', galaxyTitle: '이번 매칭 성계', galaxyFit: '보기 초기화',
      galaxyNote: 'B1–B8과 필요／제공 가능 항목은 AI 추론입니다(소유자 미확인). evidence는 계획 이념 원문입니다. 1기에는 추천하거나 자동으로 연락하지 않습니다.',
      refresh: '진행 상황 새로고침', again: '새 매칭 시작', fetched: list => `읽음: ${list.join(', ')}`,
      status: {CLARIFY_FIRST: '먼저 정보 보완', EXPLORE: '탐색 가능', ELIGIBLE: '순위만·제안 없음', RECOMMEND: '추천', EXCLUDED: '범위 밖'},
      errors: {interrupted: '매칭이 중단되었습니다. "새 매칭 시작"을 누르세요.',
        listFailed: '프로젝트 목록을 불러오지 못했습니다. "새 매칭 시작"을 눌러 다시 시도하세요.',
        notEnough: '매칭에는 A와 최소 2개 대상이 필요하지만 사용할 수 있는 프로젝트가 부족합니다.',
        noInitiable: '이 사이트에서 매칭을 시작할 수 있는 프로젝트가 아직 없습니다(이 사이트에서 관리하는 프로젝트만 초대를 보낼 수 있습니다).',
        unreadable: '프로젝트 중 하나를 읽을 수 없습니다. "새 매칭 시작"을 누르세요.', pickA: '먼저 내 프로젝트 A를 선택하세요.',
        targets: '비교 대상 2–4개를 다시 선택하세요.', failed: '매칭에 실패했습니다. 잠시 후 "새 매칭 시작"을 누르세요.'},
    },
  };
  window.__MATCH_I18N = MATCH_I18N;
  // 伺服器錯誤是中文原句；外文介面依句型換成同義的固定說明。
  const ERROR_KINDS = [[/已中斷/, 'interrupted'], [/讀取專案清單失敗/, 'listFailed'], [/至少\s*\d+\s*個對象/, 'notEnough'],
    [/還沒有可以發起媒合|不能在本站發起媒合/, 'noInitiable'], [/無法讀取其中一個專案/, 'unreadable'],
    [/請先選擇你的專案/, 'pickA'], [/媒合對象/, 'targets']];
  const LANG_ALIAS = {zh: 'zh', en: 'en', ja: 'ja', jp: 'ja', ko: 'ko', kr: 'ko'};
  const normLang = v => LANG_ALIAS[String(v || '').trim().toLowerCase().split(/[-_]/)[0]] || null;
  const cookieLang = () => {
    const m = document.cookie.match(/(?:^|;\s*)eva_lang=([^;]*)/);
    try { return m ? normLang(decodeURIComponent(m[1])) : null; } catch (_) { return null; }
  };

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
    .live-match .mt-note{color:#5f6b7a;font-size:12px}
    .live-match .mt-search{display:block;width:100%;box-sizing:border-box;margin:2px 0 6px;padding:6px 10px;border:1px solid #9aa5b1;border-radius:8px;font:inherit}
    .live-match .mt-box label.mt-pick{display:flex;align-items:center;gap:8px;margin:0;padding:3px 4px;border-radius:6px;cursor:pointer}
    .live-match .mt-box label.mt-pick[hidden]{display:none}
    .live-match .mt-pick input{flex:none;margin:0}
    .live-match .mt-pick-text{display:flex;flex-direction:column;min-width:0}
    .live-match .mt-pick-sub{font-size:12px;color:#7b8794;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .live-match .mt-compare-scroll{overflow-x:auto;max-width:100%}
    /* #234 手機：點擊目標 ≥ 44px、勾選整列可點、表格橫向捲動不撐破版面。 */
    @media(max-width:760px){
      .live-match .mt-box{padding:8px 0;min-width:0}
      .live-match .mt-box fieldset{min-width:0}
      .live-match .mt-box label.mt-pick{min-height:44px;padding:4px 6px}
      .live-match .mt-pick input{width:22px;height:22px}
      .live-match .mt-box button,.live-match .mt-box select,.live-match .mt-search{min-height:44px;min-width:44px}
      .live-match .mt-box select{max-width:100%}
      .live-match .mt-galaxy iframe{height:420px}
    }
    /* #229 真實媒合任務不用雲林示範的選案、比較與「確認並開始分析」：整段收起，只留本任務面板。 */
    .live-match .desk .analysis{display:none!important}`;
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
  let lang = cookieLang() || 'zh';
  let T = MATCH_I18N[lang];
  const HAN = /[\u3400-\u9fff]/;
  const errorText = e => {
    if (lang === 'zh' || !HAN.test(String(e))) return e;
    const hit = ERROR_KINDS.find(([re]) => re.test(e));
    return T.errors[hit ? hit[1] : 'failed'];
  };
  // 工作區外框（embed.html）的標籤：只有外文才換，zh 保持原樣。
  const localizeDesk = () => {
    if (lang === 'zh') return;
    const desk = mount.closest('.desk');
    if (!desk) return;
    desk.setAttribute('aria-label', T.desk);
    const btns = desk.querySelectorAll('.desk-actions button');
    for (const b of btns) b.textContent = b.classList.contains('mobile-toggle') ? T.chat : T.collapse;
  };
  setTitle(T.match + T.workspace);
  localizeDesk();

  let snapshot = null, pending = null, controlsKey = null, frame = null, frameKey = null, shown = [], query = '';
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
      status.textContent = T.noReply;
      if (!closed) send('get');
    }, 12000);
    controlsKey = null;
    render();
    send(action, extra);
  }
  const nameOf = pid => (snapshot?.projects || []).find(p => p.uuid === pid)?.name
    || (snapshot?.result?.projects || []).find(p => p.pid === pid)?.name || pid;

  // 地點／主題：伺服器有給才顯示（欄位名稱容許幾種常見寫法）。
  const pickText = v => (Array.isArray(v) ? v.filter(Boolean).join('、') : (typeof v === 'string' ? v.trim() : ''));
  const subline = p => {
    const place = pickText(p.location ?? p.place ?? p.city ?? p.area ?? p.region);
    const topic = pickText(p.topic ?? p.topics ?? p.theme ?? p.category);
    return [place, topic].filter(Boolean).join('・');
  };

  function renderSelect(s) {
    const options = (Array.isArray(s.projects) ? s.projects : []).filter(p => p?.uuid && p?.name);
    const min = s.min_targets || 2, max = s.max_targets || 4;
    // #217：A 只能選本站可發起媒合的案（伺服器給 initiable）；對象仍是整份清單扣掉 A。
    const initiable = Array.isArray(s.initiable) ? new Set(s.initiable) : null;
    const choices = initiable ? options.filter(p => initiable.has(p.uuid)) : options;
    const label = node('label', T.projectA + ' ');
    const a = node('select', null, {'aria-label': T.projectA, 'data-match-a': ''});
    for (const p of choices) { const o = node('option', p.name); o.value = p.uuid; a.append(o); }
    if (s.a && choices.some(p => p.uuid === s.a)) a.value = s.a;
    label.append(a);
    const set = node('fieldset');
    set.append(node('legend', T.targets(min, max)));
    const checks = [];
    const start = button(T.start, () => {
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
      hint.textContent = T.picked(n);
    };
    // #234 清單上方的搜尋框：依名稱過濾（不分大小寫）；勾選狀態不受過濾影響。
    // 對象少（≤ SEARCH_MIN）時一眼看得完，不放搜尋框。
    const SEARCH_MIN = 6;
    const search = node('input', null, {type: 'search', class: 'mt-search', 'data-match-search': '',
      placeholder: T.search, 'aria-label': T.searchLabel, autocomplete: 'off'});
    search.value = query;
    const rows = [];
    const filter = () => {
      query = search.value;
      const want = query.trim().toLowerCase();
      for (const [row, name] of rows) row.hidden = !!want && !name.toLowerCase().includes(want);
    };
    search.oninput = filter;
    if (options.length > SEARCH_MIN) set.append(search);
    for (const p of options) {
      // 整列（label）都可點；名稱下一行顯示地點或主題（有資料時）。
      const row = node('label', null, {class: 'mt-pick', 'data-match-row': p.uuid});
      const c = node('input', null, {type: 'checkbox', 'data-match-target': p.uuid});
      c.value = p.uuid;
      c.checked = (s.targets || []).includes(p.uuid);
      c.onchange = sync;
      checks.push(c);
      const text = node('span', null, {class: 'mt-pick-text'});
      text.append(node('span', p.name, {class: 'mt-pick-name'}));
      const sub = subline(p);
      if (sub) text.append(node('span', sub, {class: 'mt-pick-sub', 'data-match-sub': ''}));
      row.append(c, text);
      rows.push([row, String(p.name)]);
      set.append(row);
    }
    filter();
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
    compare.append(node('h3', T.compare(pairs.length, nameOf(res.a))));
    const table = node('table'), head = node('tr'), body = node('tbody');
    for (const h of T.cols) head.append(node('th', h, {scope: 'col'}));
    const thead = node('thead'); thead.append(head); table.append(thead, body);
    for (const p of pairs) {
      const on = shown.includes(p.pb);
      const tr = node('tr', null, {'data-match-pair': p.pair, 'data-shown': on ? '1' : '0'});
      const c = p.counts || {};
      const st = lang === 'zh' ? (p.status_text || p.status) : (T.status[p.status] || p.status);
      for (const v of [nameOf(p.pb), st, c.complement ?? 0, c.third ?? 0, c.peer ?? 0]) tr.append(node('td', String(v)));
      const td = node('td');
      td.append(button(on ? T.inGalaxy : T.toGalaxy, () => focusTarget(p.pb), {'data-match-show': p.pb}));
      td.append(document.createTextNode(' '));
      td.append(button(T.askEva, () => send('explain', {pa: p.pa, pb: p.pb, kind: 'pair'}), {'data-match-explain': p.pair}));
      tr.append(td);
      body.append(tr);
    }
    const scroll = node('div', null, {class: 'mt-compare-scroll'});
    scroll.append(table);
    compare.append(scroll);
    if (pairs.length > 3) compare.append(node('p', T.galaxyLimit, {class: 'mt-note'}));
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

  // #229 星圖頁（tangle-match.html）裡唯一的介面字是「重設」按鈕的提示；依語言換掉（zh 保持原字）。
  function localizeGalaxy() {
    try {
      const fit = frame && frame.contentDocument && frame.contentDocument.getElementById('zFit');
      if (fit && fit.getAttribute('title') !== T.galaxyFit) fit.setAttribute('title', T.galaxyFit);
    } catch (_) { /* 不同源時不動 */ }
  }

  function renderGalaxy(s) {
    const res = s.status === 'done' ? s.result : null;
    const targets = res ? (res.projects || []).slice(1).map(p => p.pid) : [];
    if (res && !shown.length) shown = targets.slice(0, 3);
    window.__matchGalaxy = res;
    const key = res ? `${s.task_id}:${[res.a, ...shown].join(',')}:${lang}` : null;
    if (frameKey === key) return;
    frameKey = key;
    galaxy.replaceChildren();
    frame = null;
    if (!key) return;
    frame = node('iframe', null, {title: T.galaxyTitle, 'data-match-galaxy': ''});
    frame.addEventListener('load', postStatus);
    frame.addEventListener('load', localizeGalaxy);
    frame.src = '/public/tangle/tangle-match.html?liveMatch=1&v=live-match&t=' + encodeURIComponent(s.task_id)
      + '&ps=' + [res.a, ...shown].map(encodeURIComponent).join(',');
    galaxy.append(frame);
    galaxy.append(node('p', (lang === 'zh' ? res.note : res.note && T.galaxyNote) || '', {class: 'mt-note'}));
  }

  function render() {
    const s = snapshot || {};
    const phase = s.status || 'loading';
    const next = normLang(s.lang) || cookieLang() || 'zh';
    if (next !== lang) { lang = next; T = MATCH_I18N[lang]; localizeDesk(); }
    const text = pending ? T.pending : (T.labels[phase] || T.labels.loading);
    if (status.textContent !== text) status.textContent = text;
    setTitle(s.a ? `${T.match} / ${nameOf(s.a)}` : T.match + T.workspace);
    const key = JSON.stringify([s.task_id, phase, s.projects, s.initiable, s.error, !!pending, lang]);
    if (controlsKey !== key) {
      controlsKey = key;
      controls.replaceChildren();
      if (s.error) controls.append(node('p', errorText(s.error), {class: 'mt-error', role: 'alert'}));
      if (phase === 'select') renderSelect(s);
      if (phase === 'loading' || phase === 'running') {
        const refresh = button(T.refresh, () => send('get'));
        refresh.disabled = !s.task_id;
        controls.append(refresh);
      }
      if (phase === 'done' || phase === 'error') {
        const again = button(T.again, () => { shown = []; submit('new'); }, {'data-match-new': ''});
        again.disabled = !!pending;
        controls.append(again);
      }
    }
    renderCompare(phase === 'done' ? s.result : null);
    renderGalaxy(s);
    details.replaceChildren();
    if (phase === 'running') {
      const done = (s.progress || []).filter(p => p?.step === 'fetch').map(p => p.name);
      if (done.length) details.append(node('p', T.fetched(done)));
    }
  }

  function accept(next) {
    if (!next || typeof next !== 'object' || !next.task_id) return;
    if (snapshot?.task_id !== next.task_id || snapshot?.status !== next.status || next.error) {
      clearTimeout(pending);
      pending = null;
    }
    if (snapshot?.task_id !== next.task_id) { shown = []; frameKey = undefined; query = ''; }
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
