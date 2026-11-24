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
      inGalaxy: '在星圖中定位', toGalaxy: '放進星圖', askEva: '請 Eva 說明',
      galaxyLimit: '星圖最多同時畫 A 與 3 個對象；用「放進星圖」切換。', galaxyTitle: '本次媒合星系', galaxyFit: '重設',
      galaxyNote: 'B1–B8 與需要／能提供是 AI 推論（未經 Owner 確認）；evidence 是計畫理念原文。第一期不推薦、不自動聯絡。',
      again: '開始新媒合', fetched: list => `已讀取：${list.join('、')}`,
      steps: ['讀取計畫', '判斷需要與能提供', '比對互補', '寫建議'], count: (n, t) => `（${n}/${t}）`, judging: '判斷中',
      stale: '沒有收到新進度，按這裡重新整理', listing: '其他專案名稱補齊中…',
      status: {CLARIFY_FIRST: '先補資料', EXPLORE: '可探索', ELIGIBLE: '可排序・未建議', RECOMMEND: '推薦', EXCLUDED: '不在範圍'},
      ready: {title: '媒合準備度', checking: '正在看 A 的資料夠不夠…', icons: {ok: '✅', vague: '⚠', missing: '？'},
        state: {ok: '足夠', vague: '不夠具體', missing: '還沒寫'},
        items: {offer: '你能提供什麼', need: '你需要什麼', scale: '規模與時間', collab: '想怎麼合作'},
        hint: '資料不夠也可以直接媒合；補完推薦會更準', complete: '資料完整，可以開始',
        ask: '回答幾個問題（約 2 分鐘）', skip: '先直接媒合', other: '其他（自己寫）', stop: '先停在這',
        consent: '要不要把這段附加到你的計畫理念？（會寫進專案的計畫理念欄位；原本的文字保留不動）', yes: '要，補進去', no: '不用', send: '送出',
        otherLabel: '自己寫答案', step: (n, t) => `問題 ${n}／${t}`, answered: a => `你的回答：${a}`,
        skipped: '好，直接勾選對象開始媒合。', stopped: '先停在這；隨時可以開始媒合。', done: '謝謝！可以開始媒合了。',
        saving: '正在補進計畫理念…', savedOk: n => `已附加到計畫理念（${n} 則；原本的文字保留不動）。`,
        savedErr: n => `有 ${n} 則沒補進去，你的回答仍會用在這次媒合。`,
        nextStep: '下一步：在下方勾選 2–4 個比較對象，再按「開始媒合」。',
        previewTitle: '會附加在計畫理念最後面：', previewNote: '網站會在這段前面加一行來源標註（AI-Eva 媒合補問、你的帳號與時間）。',
        savedList: '這次附加的內容：', openPage: '到專案頁查看計畫理念 ↗'},
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
      inGalaxy: 'Locate in galaxy', toGalaxy: 'Show in galaxy', askEva: 'Ask Eva to explain',
      galaxyLimit: 'The galaxy shows A and at most 3 projects at a time; use "Show in galaxy" to switch.',
      galaxyTitle: 'Matching galaxy for this run', galaxyFit: 'Reset view',
      galaxyNote: 'B1–B8 and needs / offers are AI inferences (not confirmed by the owner); evidence is the original plan text. Phase 1 does not recommend or contact anyone automatically.',
      again: 'Start a new match', fetched: list => `Read: ${list.join(', ')}`,
      steps: ['Read plans', 'Judge needs and offers', 'Compare complements', 'Write suggestions'], count: (n, t) => ` (${n}/${t})`,
      judging: 'judging', stale: 'No new progress received. Click here to refresh.', listing: 'Loading the other project names…',
      status: {CLARIFY_FIRST: 'Add details first', EXPLORE: 'Worth exploring', ELIGIBLE: 'Rankable, not suggested',
        RECOMMEND: 'Recommended', EXCLUDED: 'Out of scope'},
      ready: {title: 'Matching readiness', checking: 'Checking whether A has enough details…', icons: {ok: '✅', vague: '⚠', missing: '？'},
        state: {ok: 'Enough', vague: 'Not specific enough', missing: 'Not written yet'},
        items: {offer: 'What you can offer', need: 'What you need', scale: 'Scale and timing', collab: 'How you want to collaborate'},
        hint: 'You can match right away even with missing details; filling them in makes suggestions more accurate',
        complete: 'Details are complete. You can start.',
        ask: 'Answer a few questions (about 2 minutes)', skip: 'Match right away', other: 'Other (write your own)', stop: 'Stop here for now',
        consent: 'Append this to your project philosophy? (It is saved into the project\'s philosophy field; your existing text stays as is)', yes: 'Yes, add it', no: 'No thanks', send: 'Send',
        otherLabel: 'Write your own answer', step: (n, t) => `Question ${n}/${t}`, answered: a => `Your answer: ${a}`,
        skipped: 'OK. Pick the projects and start matching.', stopped: 'Stopped here. You can start matching any time.',
        done: 'Thanks! You can start matching now.',
        saving: 'Adding to your project philosophy…', savedOk: n => `Appended to your project philosophy (${n} item${n === 1 ? '' : 's'}; your existing text stays as is).`,
        savedErr: n => `${n} item${n === 1 ? '' : 's'} could not be added; your answers are still used in this match.`,
        nextStep: 'Next: tick 2–4 projects to compare below, then press "Start matching".',
        previewTitle: 'Will be added at the end of your project philosophy:', previewNote: 'The site adds a source line before it (AI-Eva matching follow-up, your account and the time).',
        savedList: 'Added this time:', openPage: 'View the philosophy on the project page ↗'},
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
      inGalaxy: '星図で位置を確認', toGalaxy: '星図に入れる', askEva: 'Eva に説明してもらう',
      galaxyLimit: '星図には A と最大 3 件までを同時に表示します。「星図に入れる」で切り替えてください。',
      galaxyTitle: '今回のマッチングの星系', galaxyFit: '表示をリセット',
      galaxyNote: 'B1–B8 と「必要／提供できる」は AI の推論です（オーナー未確認）。evidence はプランの理念の原文です。第 1 期は推薦も自動連絡もしません。',
      again: '新しいマッチングを開始', fetched: list => `読み込み済み：${list.join('、')}`,
      steps: ['プランを読む', '必要／提供を判定', '補完を比較', '提案を作成'], count: (n, t) => `（${n}/${t}）`, judging: '判定中',
      stale: '新しい進み具合が届いていません。ここを押して再読み込み', listing: 'ほかのプロジェクト名を読み込んでいます…',
      status: {CLARIFY_FIRST: '先に情報を補う', EXPLORE: '検討できる', ELIGIBLE: '順位付けのみ・提案なし', RECOMMEND: 'おすすめ', EXCLUDED: '対象外'},
      ready: {title: 'マッチングの準備度', checking: 'A の情報が十分か確認しています…', icons: {ok: '✅', vague: '⚠', missing: '？'},
        state: {ok: '十分', vague: '具体性が足りない', missing: 'まだ書かれていない'},
        items: {offer: '提供できること', need: '必要としていること', scale: '規模と時期', collab: 'どう協力したいか'},
        hint: '情報が足りなくてもそのままマッチングできます。補うと提案がより正確になります', complete: '情報はそろっています。開始できます',
        ask: 'いくつかの質問に答える（約 2 分）', skip: 'このままマッチングする', other: 'その他（自分で書く）', stop: 'ここでやめておく',
        consent: 'この内容を計画の理念に追記しますか？（プロジェクトの理念欄に保存されます。元の文章はそのまま残ります）', yes: 'はい、追記する', no: 'しない', send: '送信',
        otherLabel: '自分で答えを書く', step: (n, t) => `質問 ${n}／${t}`, answered: a => `あなたの回答：${a}`,
        skipped: '相手を選んでそのままマッチングを始めてください。', stopped: 'ここでやめました。いつでもマッチングを始められます。',
        done: 'ありがとうございます。マッチングを始められます。',
        saving: '計画の理念に追記しています…', savedOk: n => `計画の理念に追記しました（${n} 件。元の文章はそのまま残っています）。`,
        savedErr: n => `${n} 件は追記できませんでした。回答は今回のマッチングに使われます。`,
        nextStep: '次へ：下で比較する案件を 2〜4 件選び、「マッチング開始」を押してください。',
        previewTitle: '計画の理念の末尾に追記される内容：', previewNote: 'サイトがこの前に出典の行（AI-Eva マッチング補足質問、アカウントと日時）を加えます。',
        savedList: '今回追記した内容：', openPage: 'プロジェクトページで理念を見る ↗'},
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
      inGalaxy: '성도에서 위치 찾기', toGalaxy: '성도에 넣기', askEva: 'Eva에게 설명 요청',
      galaxyLimit: '성도에는 A와 최대 3개 대상까지 동시에 표시됩니다. "성도에 넣기"로 전환하세요.', galaxyTitle: '이번 매칭 성계', galaxyFit: '보기 초기화',
      galaxyNote: 'B1–B8과 필요／제공 가능 항목은 AI 추론입니다(소유자 미확인). evidence는 계획 이념 원문입니다. 1기에는 추천하거나 자동으로 연락하지 않습니다.',
      again: '새 매칭 시작', fetched: list => `읽음: ${list.join(', ')}`,
      steps: ['계획 읽기', '필요／제공 판단', '보완 비교', '제안 작성'], count: (n, t) => ` (${n}/${t})`, judging: '판단 중',
      stale: '새 진행 상황을 받지 못했습니다. 여기를 눌러 새로고침하세요.', listing: '다른 프로젝트 이름을 불러오는 중…',
      status: {CLARIFY_FIRST: '먼저 정보 보완', EXPLORE: '탐색 가능', ELIGIBLE: '순위만·제안 없음', RECOMMEND: '추천', EXCLUDED: '범위 밖'},
      ready: {title: '매칭 준비도', checking: 'A의 정보가 충분한지 확인하는 중…', icons: {ok: '✅', vague: '⚠', missing: '？'},
        state: {ok: '충분', vague: '구체적이지 않음', missing: '아직 작성되지 않음'},
        items: {offer: '제공할 수 있는 것', need: '필요한 것', scale: '규모와 시기', collab: '원하는 협력 방식'},
        hint: '정보가 부족해도 바로 매칭할 수 있습니다. 보완하면 추천이 더 정확해집니다', complete: '정보가 충분합니다. 시작할 수 있습니다',
        ask: '몇 가지 질문에 답하기(약 2분)', skip: '바로 매칭하기', other: '기타(직접 작성)', stop: '여기서 멈추기',
        consent: '이 내용을 계획 이념에 추가할까요?(프로젝트 이념 칸에 저장되며, 원래 내용은 그대로 남습니다)', yes: '네, 추가하기', no: '아니요', send: '보내기',
        otherLabel: '직접 답 쓰기', step: (n, t) => `질문 ${n}／${t}`, answered: a => `내 답변: ${a}`,
        skipped: '대상을 선택하고 바로 매칭을 시작하세요.', stopped: '여기서 멈췄습니다. 언제든 매칭을 시작할 수 있습니다.',
        done: '감사합니다! 이제 매칭을 시작할 수 있습니다.',
        saving: '계획 이념에 추가하는 중…', savedOk: n => `계획 이념에 추가했습니다(${n}건, 원래 내용은 그대로 남아 있습니다).`,
        savedErr: n => `${n}건은 추가하지 못했습니다. 답변은 이번 매칭에 그대로 사용됩니다.`,
        nextStep: '다음: 아래에서 비교할 프로젝트를 2~4개 고른 뒤 "매칭 시작"을 누르세요.',
        previewTitle: '계획 이념 맨 끝에 추가될 내용:', previewNote: '사이트가 그 앞에 출처 줄(AI-Eva 매칭 보충 질문, 계정과 시간)을 덧붙입니다.',
        savedList: '이번에 추가한 내용:', openPage: '프로젝트 페이지에서 이념 보기 ↗'},
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
    .live-match .mt-stage{position:relative;height:540px;border-radius:10px;background:#0b1020;overflow:hidden}
    .live-match .mt-stage iframe{position:absolute;inset:0;width:100%;height:100%;border:0;border-radius:10px;background:#0b1020}
    .live-match .mt-stage iframe[data-match-next]{visibility:hidden}
    /* #232 步驟列：完成打勾、進行中呼吸；手機上星圖縮矮，步驟列＋星球同在第一屏 */
    .live-match .mt-steps{display:flex;flex-wrap:wrap;gap:4px 6px;margin:0;padding:0;list-style:none;font-size:13px}
    .live-match .mt-steps li{padding:3px 9px;border-radius:999px;background:#eef1f5;color:#7a8594;white-space:nowrap}
    .live-match .mt-steps li+li::before{content:'→';margin-right:6px;color:#b5bdc8}
    .live-match .mt-steps li[data-state="done"]{background:#e3f4ea;color:#21714a}
    .live-match .mt-steps li[data-state="done"]::after{content:' ✓'}
    .live-match .mt-steps li[data-state="active"]{background:#dde8fb;color:#1d4fa8;font-weight:600;animation:mt-pulse 1.2s ease-in-out infinite}
    @keyframes mt-pulse{0%,100%{box-shadow:0 0 0 0 rgba(47,107,214,.45)}50%{box-shadow:0 0 0 5px rgba(47,107,214,0)}}
    @keyframes mt-fade{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
    .live-match .mt-fade{animation:mt-fade .6s ease-out both}
    .live-match .mt-stale{background:none;border:0;padding:0;color:#b4bfcc;font-size:12px;text-decoration:underline;cursor:pointer;align-self:flex-start}
    @media (max-width:640px){.live-match .mt-box{padding:8px 10px;gap:8px}.live-match .mt-stage{height:min(400px,46vh)}
      .live-match .mt-steps{font-size:12px}.live-match .mt-steps li{padding:2px 7px}}
    @media (prefers-reduced-motion:reduce){.live-match .mt-steps li[data-state="active"],.live-match .mt-fade{animation:none}}
    .live-match .mt-error{color:#ff8f8f}
    /* #238 媒合準備度：選好 A 先看資料夠不夠；只提示、不擋開始。#242 區塊在深色工作區（#13161c＋紫色光暈）上，文字色都要 ≥ 4.5:1 */
    .live-match .mt-ready{border:1px solid #d8dee6;border-radius:8px;padding:8px 10px;display:flex;flex-direction:column;gap:6px}
    .live-match .mt-ready ul{list-style:none;margin:0;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:2px 10px}
    .live-match .mt-ready li[data-state="ok"]{color:#5fd08f}
    .live-match .mt-ready li[data-state="vague"]{color:#f0b54a}
    .live-match .mt-ready li[data-state="missing"]{color:#b4bfcc}
    .live-match .mt-ready p{margin:0}
    .live-match .mt-ready-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
    .live-match .mt-ready-q{font-weight:600}
    .live-match .mt-ready-preview{border-left:3px solid #5fa8ff;background:rgba(95,168,255,.08);padding:6px 10px;border-radius:4px;display:flex;flex-direction:column;gap:4px}
    .live-match .mt-ready-preview blockquote{margin:0;white-space:pre-wrap;font-weight:600}
    .live-match .mt-ready ul.mt-ready-saved-list{display:block;list-style:disc;padding-left:20px}
    .live-match .mt-ready ul.mt-ready-saved-list li{color:inherit}
    .live-match .mt-ready-page{color:#5fa8ff;text-decoration:underline}
    .live-match .mt-ready input[type=text]{flex:1;min-width:160px;padding:5px 8px;border:1px solid #9aa5b1;border-radius:6px;font:inherit}
    .live-match .mt-note{color:#b4bfcc;font-size:12px}
    .live-match .mt-search{display:block;width:100%;box-sizing:border-box;margin:2px 0 6px;padding:6px 10px;border:1px solid #9aa5b1;border-radius:8px;font:inherit}
    .live-match .mt-box label.mt-pick{display:flex;align-items:center;gap:8px;margin:0;padding:3px 4px;border-radius:6px;cursor:pointer}
    .live-match .mt-box label.mt-pick[hidden]{display:none}
    .live-match .mt-pick input{flex:none;margin:0}
    .live-match .mt-pick-text{display:flex;flex-direction:column;min-width:0}
    .live-match .mt-pick-sub{font-size:12px;color:#aab4c0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
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
  const steps = node('ol', null, {class: 'mt-steps', 'data-match-steps': ''});
  const galaxy = node('div', null, {class: 'mt-galaxy'});
  const details = node('div');
  box.append(status, steps, controls, compare, galaxy, details);
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
  // #232：沒有「更新進度」鈕；超過 STALE_MS 沒收到新進度才出現一行小字讓使用者手動重新整理。
  const STALE_MS = 30000;
  let staleTimer = null, stale = false, progressKey = null, draft = null, cardsFor = null;
  // #238 準備度：面板自己的流程狀態（panel／ask／skip／stopped／done）；asked 記已向伺服器要過的 task+A
  let ready = null, readyAsked = null;
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
    // #232 清單會邊補名稱邊重畫：保留使用者剛選的 A 與勾選
    const mine = draft?.task === s.task_id ? draft : null;
    const wantA = mine?.a ?? s.a;
    if (wantA && choices.some(p => p.uuid === wantA)) a.value = wantA;
    label.append(a);
    const set = node('fieldset');
    set.append(node('legend', T.targets(min, max)));
    const checks = [];
    const start = button(T.start, () => {
      const targets = checks.filter(c => c.checked).map(c => c.value);
      draft = null;
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
    const touch = () => {
      sync();
      draft = {task: s.task_id, a: a.value, targets: checks.filter(c => c.checked).map(c => c.value)};
    };
    for (const p of options) {
      // 整列（label）都可點；名稱下一行顯示地點或主題（有資料時）。
      const row = node('label', null, {class: 'mt-pick', 'data-match-row': p.uuid});
      const c = node('input', null, {type: 'checkbox', 'data-match-target': p.uuid});
      c.value = p.uuid;
      c.checked = (mine ? mine.targets : s.targets || []).includes(p.uuid);
      c.onchange = touch;
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
    const readyBox = node('div', null, {class: 'mt-ready', 'data-match-readiness': ''});
    const askReady = () => {
      const want = a.value;
      if (!want || pending || s.status !== 'select') return;
      const k = `${s.task_id}|${want}`;
      if (s.readiness?.a === want && s.readiness.state !== 'checking') { readyAsked = k; return; }
      if (readyAsked === k) return;
      readyAsked = k;
      send('readiness', {a: want});
    };
    a.onchange = () => { touch(); askReady(); renderReady(readyBox, s, a.value, set); };
    a.disabled = !!pending;
    controls.append(label, readyBox, set, start, hint);
    renderReady(readyBox, s, a.value, set);
    askReady();
    if (s.listing) controls.append(node('p', T.listing, {class: 'mt-note', 'data-match-listing': ''}));
    sync();
  }

  // #238 媒合準備度：四項（✅／⚠／？）；不足時給兩個選擇，補問一次一題（最多 3 題）。永遠不擋「開始媒合」。
  function renderReady(box, s, aId, targetsEl) {
    box.replaceChildren();
    const R = T.ready;
    const r = s.readiness?.a === aId ? s.readiness : null;
    if (!aId || !r || r.state === 'error') { box.hidden = true; return; }
    box.hidden = false;
    if (r.state !== 'ready') { box.append(node('p', R.checking, {class: 'mt-note', 'data-match-ready-checking': ''})); return; }
    const tx = R;   // 面板依目前語言用自己的四語表（伺服器的 r.texts 與之同義，僅供其他前端用）
    if (r.complete) { box.append(node('p', `✅ ${tx.complete}`, {'data-match-ready-complete': ''})); return; }
    const key = `${s.task_id}|${aId}`;
    if (ready?.key !== key) ready = {key, mode: 'panel', step: 0, picked: null, other: false};
    const redo = () => renderReady(box, s, aId, targetsEl);
    const list = node('ul', null, {'aria-label': R.title});
    for (const it of r.items || []) {
      const label = it.label || R.items[it.key] || it.key;
      const li = node('li', `${R.icons[it.state] || ''} ${label}：${R.state[it.state] || ''}`,
        {'data-match-ready': it.key, 'data-state': it.state});
      list.append(li);
    }
    box.append(list, node('p', tx.hint, {class: 'mt-note', 'data-match-ready-msg': ''}));
    const qs = (Array.isArray(r.questions) ? r.questions : []).slice(0, 3);
    const stop = () => button(tx.stop, () => { ready.mode = 'stopped'; redo(); }, {'data-match-ready-stop': ''});
    if (ready.mode === 'panel') {
      const row = node('div', null, {class: 'mt-ready-row'});
      if (qs.length) row.append(button(tx.ask, () => { ready.mode = 'ask'; ready.step = 0; ready.picked = null; redo(); },
        {'data-match-ready-ask': ''}));
      row.append(button(tx.skip, () => {
        ready.mode = 'skip'; redo();
        targetsEl.querySelector('input:not([disabled])')?.focus();
      }, {'data-match-ready-skip': ''}));
      box.append(row);
      return;
    }
    if (ready.mode !== 'ask') {
      const note = {skip: R.skipped, stopped: R.stopped, done: R.done}[ready.mode];
      if (note) box.append(node('p', note, {class: 'mt-note', 'data-match-ready-note': ready.mode}));
      // 「要，補進去」的結果：伺服器寫回後在 readiness.saved 標 ok／error（沒回來前顯示「正在補進」）
      const asked = ready.consented || [];
      if (asked.length) {
        const saved = r.saved || {};
        const ok = asked.filter(k => saved[k] === 'ok').length;
        const err = asked.filter(k => saved[k] === 'error').length;
        if (asked.length - ok - err) box.append(node('p', R.saving, {class: 'mt-note', 'data-match-ready-saved': 'saving'}));
        if (ok) {
          box.append(node('p', `✅ ${R.savedOk(ok)}`, {'data-match-ready-saved': 'ok'}));
          const lines = asked.map(k => (r.saved_text || {})[k]).filter(Boolean);
          if (lines.length) {
            const list = node('ul', null, {class: 'mt-ready-saved-list', 'data-match-ready-saved-list': '', 'aria-label': R.savedList});
            for (const t of lines) list.append(node('li', t));
            box.append(node('p', R.savedList, {class: 'mt-note'}), list);
          }
          if (typeof r.page === 'string' && /^https:\/\//.test(r.page)) {
            const link = node('a', R.openPage, {href: r.page, target: '_blank', rel: 'noopener noreferrer',
              class: 'mt-ready-page', 'data-match-ready-page': ''});
            const linkRow = node('p', null);
            linkRow.append(link);
            box.append(linkRow);
          }
        }
        if (err) box.append(node('p', `⚠ ${R.savedErr(err)}`, {'data-match-ready-saved': 'error'}));
      }
      if (ready.mode === 'done' || ready.mode === 'stopped') {
        box.append(node('p', R.nextStep, {class: 'mt-ready-q', 'data-match-ready-next': ''}));
        if (!ready.pointed) {
          ready.pointed = true;
          setTimeout(() => {
            targetsEl.scrollIntoView({block: 'start'});
            targetsEl.querySelector('input:not([disabled])')?.focus({preventScroll: true});
          }, 0);
        }
      }
      return;
    }
    const q = qs[ready.step];
    if (!q) { ready.mode = 'done'; redo(); return; }
    const next = () => { ready.step++; ready.picked = null; ready.other = false; if (ready.step >= qs.length) ready.mode = 'done'; redo(); };
    box.append(node('p', R.step(ready.step + 1, qs.length), {class: 'mt-note', 'data-match-ready-step': ''}),
      node('p', q.text, {class: 'mt-ready-q', 'data-match-ready-question': q.key}));
    if (ready.picked == null) {
      const row = node('div', null, {class: 'mt-ready-row'});
      (q.options || []).slice(0, 4).forEach((o, i) => row.append(button(o, () => { ready.picked = o; redo(); },
        {'data-match-ready-opt': String(i)})));
      row.append(button(tx.other, () => { ready.other = true; redo(); }, {'data-match-ready-other': ''}));
      box.append(row);
      if (ready.other) {
        const own = node('div', null, {class: 'mt-ready-row'});
        const input = node('input', null, {type: 'text', 'aria-label': R.otherLabel, 'data-match-ready-input': ''});
        const go = button(R.send, () => { const v = input.value.trim(); if (v) { ready.picked = v; redo(); } },
          {'data-match-ready-send': ''});
        input.onkeydown = e => { if (e.key === 'Enter') go.click(); };
        own.append(input, go);
        box.append(own);
        input.focus();
      }
      const row2 = node('div', null, {class: 'mt-ready-row'});
      row2.append(stop());
      box.append(row2);
      return;
    }
    // #201：回答後問要不要補進計畫理念；同意才寫回（伺服器走既有寫回流程，只附加不改原文）
    box.append(node('p', R.answered(ready.picked), {'data-match-ready-answer': ''}),
      node('p', tx.consent, {class: 'mt-ready-q', 'data-match-ready-consent': ''}));
    // 送出前預覽：實際會送去附加的那一段（寫回固定用中文項目名，與伺服器 writeback_text 相同）
    const preview = node('div', null, {class: 'mt-ready-preview', 'data-match-ready-preview': ''});
    preview.append(node('p', R.previewTitle, {class: 'mt-note'}),
      node('blockquote', `${q.write_label || q.key}：${ready.picked}`, {'data-match-ready-preview-text': ''}),
      node('p', R.previewNote, {class: 'mt-note'}));
    box.append(preview);
    const row = node('div', null, {class: 'mt-ready-row'});
    row.append(button(R.yes, () => {
      send('ready_answer', {a: aId, key: q.key, answer: ready.picked, consent: true});
      ready.consented = [...(ready.consented || []), q.key];
      next();
    }, {'data-match-ready-yes': ''}), button(R.no, next, {'data-match-ready-no': ''}), stop());
    box.append(row);
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
      const explanation = node('p', '', {role: 'status', 'data-match-explanation': ''});
      explanation.hidden = true;
      td.append(button(T.askEva, () => {
        const counts = [c.complement ?? 0, c.third ?? 0, c.peer ?? 0];
        const none = counts.every(n => n === 0);
        const empty = {
          zh: '目前沒有足夠依據判定這兩案能互補、共同尋找第三方，或聯合交流。',
          en: 'This run found no evidence of complementarity, a shared third-party need, or opportunities to collaborate.',
          ja: '今回の結果では、補完関係、第三者を共同で探す必要性、連携・交流を示す根拠はありません。',
          ko: '이번 결과에서는 상호 보완, 공동으로 제3자를 찾을 필요성, 협력·교류의 근거가 확인되지 않았습니다.',
        };
        explanation.hidden = false;
        explanation.textContent = `${nameOf(p.pa)} × ${nameOf(p.pb)} — ${st}. ` +
          (none ? empty[lang] : counts.map((n, i) => `${T.cols[i + 2]}: ${n}`).join(' · '));
        send('explain', {pa: p.pa, pb: p.pb, kind: 'pair'});
      }, {'data-match-explain': p.pair}), explanation);
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
    if (!targets.includes(pid)) return;
    if (!shown.includes(pid)) {
      shown = [pid, ...shown].slice(0, 3);
      shown = targets.filter(t => shown.includes(t));
      frameKey = undefined;
      render();
    }
    const target = galaxy.querySelector('iframe[data-match-next]') || frame;
    if (!target) return;
    target.parentElement.scrollIntoView({block: 'start', behavior: 'instant'});
    const locate = () => {
      if (frame === target && target.isConnected) {
        target.contentWindow.postMessage({type: 'mf-locate', pid}, location.origin);
      }
    };
    if (loadedGalaxyFrames.has(target)) locate();
    else target.addEventListener('load', locate, {once: true});
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

  // #229 星圖頁「重設」按鈕的提示依語言換掉（zh 保持原字）；#249 起星圖頁其餘字由 ?lang＋galaxy-i18n.js 自己換。
  function localizeGalaxy() {
    try {
      const fit = frame && frame.contentDocument && frame.contentDocument.getElementById('zFit');
      if (fit && fit.getAttribute('title') !== T.galaxyFit) fit.setAttribute('title', T.galaxyFit);
    } catch (_) { /* 不同源時不動 */ }
  }

  // #232 判斷中先畫星球：伺服器每推一次 preview（讀到的案先出現、判完的帶 B1–B8 衛星亮起）就換一張星圖；
  // 新的 iframe 先在背後載入，載好才換上，畫面不會閃黑。完成後換成真正的結果（同一套畫法）。
  function galaxyData(s) {
    if (s.status === 'done' && s.result) return s.result;
    const pv = s.status === 'running' ? s.preview : null;
    if (!pv || !Array.isArray(pv.projects) || !pv.projects.length) return null;
    return {...pv, projects: pv.projects.map(p => p.judged ? p : {...p, name: `${p.name}（${T.judging}）`})};
  }

  const loadedGalaxyFrames = new WeakSet();
  function renderGalaxy(s) {
    const res = galaxyData(s);
    const live = !!res?.preview;
    const targets = res ? (res.projects || []).slice(1).map(p => p.pid) : [];
    if (live) shown = targets.slice(0, 3);
    else if (res && !shown.length) shown = targets.slice(0, 3);
    const ps = res ? [res.a, ...shown] : [];
    const lit = live ? res.projects.filter(p => p.judged).map(p => p.pid).join(',') : 'done';
    const key = res ? `${s.task_id}:${ps.join(',')}:${lit}:${lang}` : null;
    if (frameKey === key) return;
    frameKey = key;
    if (!key) { galaxy.replaceChildren(); frame = null; window.__matchGalaxy = null; return; }
    window.__matchGalaxy = res;
    let stage = galaxy.querySelector('.mt-stage');
    if (!stage) {
      stage = node('div', null, {class: 'mt-stage', 'data-match-stage': ''});
      galaxy.replaceChildren(stage, node('p', '', {class: 'mt-note'}));
    }
    galaxy.querySelector('.mt-note').textContent = live ? '' : (lang === 'zh' ? res.note : res.note && T.galaxyNote) || '';
    for (const old of stage.querySelectorAll('iframe[data-match-next]')) old.remove();
    const next = node('iframe', null, {title: T.galaxyTitle});
    next.addEventListener('load', () => loadedGalaxyFrames.add(next), {once: true});
    const swap = () => {
      if (!next.isConnected) return;
      for (const old of stage.querySelectorAll('iframe')) if (old !== next) old.remove();
      next.removeAttribute('data-match-next');
      next.setAttribute('data-match-galaxy', '');
      frame = next;
      postStatus();
      localizeGalaxy();
    };
    if (frame && frame.isConnected) { next.setAttribute('data-match-next', ''); next.addEventListener('load', swap); }
    else {
      stage.replaceChildren();
      next.setAttribute('data-match-galaxy', '');
      frame = next;
      next.addEventListener('load', () => { if (frame === next) { postStatus(); localizeGalaxy(); } });
    }
    next.src = '/public/tangle/tangle-match.html?liveMatch=1&v=live-match&t=' + encodeURIComponent(s.task_id)
      + '&lang=' + encodeURIComponent(lang) + '&ps=' + ps.map(encodeURIComponent).join(',');
    stage.append(next);
  }

  // #232 步驟列：① 讀取計畫（2/5）→ ② 判斷需要與能提供（1/5）→ ③ 比對互補 → ④ 寫建議
  function renderSteps(s) {
    const phase = s.status;
    if (phase !== 'running' && phase !== 'done') { steps.replaceChildren(); steps.hidden = true; return; }
    const prog = Array.isArray(s.progress) ? s.progress : [];
    const total = (Array.isArray(s.targets) ? s.targets.length : 0) + 1;
    const count = step => new Set(prog.filter(p => p?.step === step).map(p => p.uuid)).size;
    const fetched = count('fetch'), judged = count('judge');
    const done = phase === 'done';
    const compared = done || prog.some(p => p?.step === 'compare' || p?.step === 'cards');
    const judgedAll = compared || prog.some(p => p?.step === 'judged') || judged >= total;
    const fetchedAll = judgedAll || judged > 0 || fetched >= total;
    const state = [fetchedAll, judgedAll, compared, done];
    const active = state.indexOf(false);
    const items = T.steps.map((label, i) => {
      const n = i === 0 ? fetched : i === 1 ? judged : null;
      const text = '①②③④'[i] + ' ' + label + (n != null && !state[i] ? T.count(n, total) : '');
      return [text, state[i] ? 'done' : i === active ? 'active' : 'todo'];
    });
    const key = JSON.stringify(items);
    if (steps.dataset.key === key) return;
    steps.dataset.key = key;
    steps.hidden = false;
    steps.replaceChildren(...items.map(([text, st], i) =>
      node('li', text, {'data-step': ['fetch', 'judge', 'compare', 'cards'][i], 'data-state': st,
        ...(st === 'active' ? {'aria-current': 'step'} : {})})));
  }

  // #232 30 秒沒收到新進度 → 小字「沒有收到新進度，按這裡重新整理」（不再常駐「更新進度」鈕）
  function watchStale(s) {
    const busy = s.status === 'loading' || s.status === 'running' || !!s.listing;
    const k = JSON.stringify([s.task_id, s.status, (s.progress || []).length, (s.projects || []).length, !!s.listing]);
    if (!busy) { clearTimeout(staleTimer); staleTimer = null; progressKey = k; if (stale) { stale = false; controlsKey = null; } return; }
    if (k === progressKey && (staleTimer || stale)) return;
    progressKey = k;
    if (stale) { stale = false; controlsKey = null; }
    clearTimeout(staleTimer);
    staleTimer = setTimeout(() => { staleTimer = null; stale = true; controlsKey = null; render(); }, STALE_MS);
  }

  // #232 建議卡出現：淡入，並捲到第一張卡（每個任務只捲一次）
  function revealCards() {
    const first = box.querySelector('[data-match-card]');
    if (!first || snapshot?.status !== 'done' || cardsFor === snapshot.task_id) return;
    cardsFor = snapshot.task_id;
    const wrap = first.closest('[data-match-cards]') || first.parentNode;
    for (const el of wrap.querySelectorAll('[data-match-card]')) el.classList.add('mt-fade');
    requestAnimationFrame(() => first.scrollIntoView({behavior: 'smooth', block: 'start'}));
  }
  new MutationObserver(revealCards).observe(box, {childList: true, subtree: true});

  function render() {
    const s = snapshot || {};
    const phase = s.status || 'loading';
    const next = normLang(s.lang) || cookieLang() || 'zh';
    if (next !== lang) { lang = next; T = MATCH_I18N[lang]; localizeDesk(); }
    const text = pending ? T.pending : (T.labels[phase] || T.labels.loading);
    if (status.textContent !== text) status.textContent = text;
    setTitle(s.a ? `${T.match} / ${nameOf(s.a)}` : T.match + T.workspace);
    watchStale(s);
    const key = JSON.stringify([s.task_id, phase, s.projects, s.initiable, s.listing, s.error, !!pending, lang, stale,
      phase === 'select' ? s.readiness || null : null]);
    if (controlsKey !== key) {
      controlsKey = key;
      controls.replaceChildren();
      if (s.error) controls.append(node('p', errorText(s.error), {class: 'mt-error', role: 'alert'}));
      if (phase === 'select') renderSelect(s);
      if (stale && s.task_id) {
        controls.append(button(T.stale, () => {
          stale = false; controlsKey = null; progressKey = null; render(); send('get');
        }, {class: 'mt-stale', 'data-match-stale': ''}));
      }
      if (phase === 'done' || phase === 'error') {
        const again = button(T.again, () => { shown = []; submit('new'); }, {'data-match-new': ''});
        again.disabled = !!pending;
        controls.append(again);
      }
    }
    renderSteps(s);
    renderCompare(phase === 'done' ? s.result : null);
    renderGalaxy(s);
    revealCards();
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
    if (snapshot?.task_id !== next.task_id || (next.status === 'done' && snapshot?.status !== 'done')) {
      shown = []; frameKey = undefined;
    }
    if (snapshot?.task_id !== next.task_id) query = '';
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
