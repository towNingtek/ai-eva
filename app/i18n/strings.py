"""AI-Eva 固定文字字串表（zh／en／ja／ko）。

規則：每個鍵四種語言都要有（tests/test_i18n_session.py 會掃描，缺一種就紅）。
佔位符用 str.format 的 `{name}`，四種語言的佔位符集合必須一致。
"""
from __future__ import annotations

# ── 工具按鈕 / 命令選單標籤（key = app id，對應 app/apps/<id>/meta.py）──────────
APP_LABELS: dict[str, dict[str, str]] = {
    "regulation_check": {"zh": "法規檢核", "en": "Regulation check", "ja": "法規チェック", "ko": "법규 검토"},
    "chart_analysis": {"zh": "圖表查詢", "en": "Chart query", "ja": "グラフ照会", "ko": "차트 조회"},
    "project_match": {"zh": "專案媒合", "en": "Project matching", "ja": "プロジェクトマッチング", "ko": "프로젝트 매칭"},
    "social_post": {"zh": "社群貼文", "en": "Social post", "ja": "SNS投稿", "ko": "소셜 게시물"},
    "web_search": {"zh": "網頁搜尋", "en": "Web search", "ja": "ウェブ検索", "ko": "웹 검색"},
    "knowledge_base": {"zh": "法規知識庫", "en": "Regulation library", "ja": "法規ナレッジベース", "ko": "법규 지식베이스"},
    "hello_world": {"zh": "模型對照", "en": "Model comparison", "ja": "モデル比較", "ko": "모델 비교"},
    "plain_chat": {"zh": "對話", "en": "Chat", "ja": "チャット", "ko": "대화"},
}

# ── 固定文字 ─────────────────────────────────────────────────────────
STRINGS: dict[str, dict[str, str]] = {
    # 歡迎訊息
    "welcome.sso": {
        "zh": "嗨，我是你在 CMS 的 AI 副駕（{who}）。\n\n"
              "我可以幫你查：{tools}。\n"
              "試試問「**列出我的專案**」或「**我的 SROI**」。\n\n"
              "或直接點下面的工具：",
        "en": "Hi, I'm your AI copilot for the CMS ({who}).\n\n"
              "I can help you with: {tools}.\n"
              "Try asking \"**List my projects**\" or \"**My SROI**\".\n\n"
              "Or just click one of the tools below:",
        "ja": "こんにちは、CMS の AI アシスタントです（{who}）。\n\n"
              "お手伝いできること：{tools}。\n"
              "「**プロジェクト一覧を見せて**」や「**私の SROI**」と聞いてみてください。\n\n"
              "または下のツールをクリックしてください：",
        "ko": "안녕하세요, CMS의 AI 코파일럿입니다（{who}）.\n\n"
              "도와드릴 수 있는 것: {tools}.\n"
              "\"**내 프로젝트 목록**\" 또는 \"**내 SROI**\"라고 물어보세요.\n\n"
              "또는 아래 도구를 바로 클릭하세요:",
    },
    "welcome.no_tools": {
        "zh": "（目前無可用工具）",
        "en": "(no tools available yet)",
        "ja": "（現在利用できるツールはありません）",
        "ko": "(현재 사용 가능한 도구 없음)",
    },
    "welcome.guest": {
        "zh": "嗨，我是 **Eva**。\n\n"
              "- 直接輸入問題 → 一般對話（OpenAI gpt-4o-mini）\n"
              "- 或直接點下面的工具：",
        "en": "Hi, I'm **Eva**.\n\n"
              "- Type a question → general chat (OpenAI gpt-4o-mini)\n"
              "- Or click one of the tools below:",
        "ja": "こんにちは、**Eva** です。\n\n"
              "- 質問を入力 → 一般的な会話（OpenAI gpt-4o-mini）\n"
              "- または下のツールをクリック：",
        "ko": "안녕하세요, **Eva**입니다.\n\n"
              "- 질문을 입력 → 일반 대화（OpenAI gpt-4o-mini）\n"
              "- 또는 아래 도구를 클릭하세요:",
    },
    # 工具派工 / 守門
    "app.not_found": {
        "zh": "⚠️ 找不到工具 `{app_id}`。",
        "en": "⚠️ Tool `{app_id}` not found.",
        "ja": "⚠️ ツール `{app_id}` が見つかりません。",
        "ko": "⚠️ 도구 `{app_id}`을(를) 찾을 수 없습니다.",
    },
    "app.opening": {
        "zh": "▶ {label}", "en": "▶ {label}", "ja": "▶ {label}", "ko": "▶ {label}",
    },
    "guard.not_enabled": {
        "zh": "⚠️「{app}」在此環境（{project}）尚未啟用。",
        "en": "⚠️ \"{app}\" is not enabled in this environment ({project}).",
        "ja": "⚠️「{app}」はこの環境（{project}）ではまだ有効になっていません。",
        "ko": "⚠️ \"{app}\"은(는) 이 환경（{project}）에서 아직 활성화되지 않았습니다.",
    },
    "guard.default_project": {
        "zh": "預設", "en": "default", "ja": "デフォルト", "ko": "기본",
    },
    "guard.role_denied": {
        "zh": "⚠️ 你的帳號權限無法使用「{app}」。",
        "en": "⚠️ Your account does not have permission to use \"{app}\".",
        "ja": "⚠️ お使いのアカウントには「{app}」を利用する権限がありません。",
        "ko": "⚠️ 계정 권한으로는 \"{app}\"을(를) 사용할 수 없습니다.",
    },
    "law.need_sso": {
        "zh": "⚠️ 請先從 CMS 重新進入 AI-Eva（法規檢核需要讀取你的專案）。",
        "en": "⚠️ Please re-enter AI-Eva from the CMS first (regulation check needs to read your projects).",
        "ja": "⚠️ まず CMS から AI-Eva に入り直してください（法規チェックにはプロジェクトの読み取りが必要です）。",
        "ko": "⚠️ 먼저 CMS에서 AI-Eva에 다시 들어와 주세요（법규 검토는 프로젝트를 읽어야 합니다）.",
    },
    "no_handler": {
        "zh": "⚠️ 沒有可用的處理器",
        "en": "⚠️ No handler available",
        "ja": "⚠️ 利用可能なハンドラーがありません",
        "ko": "⚠️ 사용 가능한 처리기가 없습니다",
    },
    # 確認 / 動作按鈕
    "btn.confirm": {"zh": "✅ 確認", "en": "✅ Confirm", "ja": "✅ 確認", "ko": "✅ 확인"},
    "btn.cancel": {"zh": "✖ 取消", "en": "✖ Cancel", "ja": "✖ キャンセル", "ko": "✖ 취소"},
    "btn.sroi_yes": {
        "zh": "✅ 產 SROI 草稿", "en": "✅ Draft SROI", "ja": "✅ SROI 草案を作成", "ko": "✅ SROI 초안 작성",
    },
    "btn.sroi_no": {"zh": "✖ 不用", "en": "✖ No thanks", "ja": "✖ 不要", "ko": "✖ 괜찮아요"},
    "btn.attach_create": {
        "zh": "📄 建成專案", "en": "📄 Create project", "ja": "📄 プロジェクト作成", "ko": "📄 프로젝트 만들기",
    },
    "btn.attach_summarize": {
        "zh": "📝 幫我摘要", "en": "📝 Summarize", "ja": "📝 要約する", "ko": "📝 요약하기",
    },
    "btn.attach_dismiss": {
        "zh": "💤 先放著", "en": "💤 Later", "ja": "💤 後で", "ko": "💤 나중에",
    },
    # 附件
    "attach.default_name": {"zh": "檔案", "en": "file", "ja": "ファイル", "ko": "파일"},
    "attach.truncated": {
        "zh": "\n…（內容過長已截斷）",
        "en": "\n…(content too long, truncated)",
        "ja": "\n…（内容が長すぎるため省略しました）",
        "ko": "\n…(내용이 너무 길어 잘렸습니다)",
    },
    "attach.unreadable": {
        "zh": "檔案讀不到內容（可能是空檔或編碼問題），請確認後再試。",
        "en": "Couldn't read the file (it may be empty or have an encoding issue). Please check and try again.",
        "ja": "ファイルの内容を読み取れませんでした（空ファイルか文字コードの問題かもしれません）。確認して再度お試しください。",
        "ko": "파일 내용을 읽을 수 없습니다（빈 파일이거나 인코딩 문제일 수 있음）. 확인 후 다시 시도해 주세요.",
    },
    "attach.unsupported_note": {
        "zh": "\n（{names} 目前還不能解析 —— 目前支援 .txt / .md、PDF 與 .docx）",
        "en": "\n({names} can't be parsed yet — supported: .txt / .md, PDF and .docx)",
        "ja": "\n（{names} はまだ解析できません —— 対応形式：.txt / .md、PDF、.docx）",
        "ko": "\n（{names}은(는) 아직 분석할 수 없습니다 —— 지원 형식: .txt / .md, PDF, .docx）",
    },
    "attach.unsupported": {
        "zh": "我收到檔案了，但這種格式目前還不能處理。{note}",
        "en": "I got the file, but I can't handle this format yet.{note}",
        "ja": "ファイルを受け取りましたが、この形式にはまだ対応していません。{note}",
        "ko": "파일을 받았지만 이 형식은 아직 처리할 수 없습니다.{note}",
    },
    "attach.received": {
        "zh": "收到檔案：{names}。我先放著、還沒打開它 —— 要我拿它做什麼？{note}",
        "en": "Got the file: {names}. I'm holding it without opening it yet — what should I do with it?{note}",
        "ja": "ファイルを受け取りました：{names}。まだ開いていません —— どうしますか？{note}",
        "ko": "파일을 받았습니다: {names}. 아직 열지 않고 보관 중입니다 —— 무엇을 할까요?{note}",
    },
    "attach.error": {
        "zh": "⚠️ 處理附件時出錯（{err}），請再試一次。",
        "en": "⚠️ Error while handling the attachment ({err}). Please try again.",
        "ja": "⚠️ 添付ファイルの処理中にエラーが発生しました（{err}）。もう一度お試しください。",
        "ko": "⚠️ 첨부 파일 처리 중 오류가 발생했습니다（{err}）. 다시 시도해 주세요.",
    },
    "attach.dismissed": {
        "zh": "好，先放著。檔案我留著，之後點上面的按鈕、或直接打字問我都行。",
        "en": "OK, I'll hold on to it. Click a button above or just type your question whenever you're ready.",
        "ja": "了解です、置いておきます。後で上のボタンを押すか、そのまま質問を入力してください。",
        "ko": "알겠습니다, 보관해 둘게요. 나중에 위 버튼을 누르거나 바로 질문을 입력하세요.",
    },
    "attach.gone": {
        "zh": "找不到剛剛的檔案了，請再上傳一次。",
        "en": "I can't find the file anymore. Please upload it again.",
        "ja": "先ほどのファイルが見つかりません。もう一度アップロードしてください。",
        "ko": "방금 파일을 찾을 수 없습니다. 다시 업로드해 주세요.",
    },
    "attach.unknown_action": {
        "zh": "這個動作我還不會，請直接打字告訴我需求。",
        "en": "I can't do that action yet. Please type what you need.",
        "ja": "その操作にはまだ対応していません。ご要望を直接入力してください。",
        "ko": "그 동작은 아직 지원하지 않습니다. 원하시는 내용을 직접 입력해 주세요.",
    },
    # Copilot / session
    "copilot.failed": {
        "zh": "⚠️ 查詢失敗，請再試一次（{err}）",
        "en": "⚠️ Query failed, please try again ({err})",
        "ja": "⚠️ 照会に失敗しました。もう一度お試しください（{err}）",
        "ko": "⚠️ 조회에 실패했습니다. 다시 시도해 주세요（{err}）",
    },
    "runtime.lost": {
        "zh": "⚠️ 目前讀不到你的 CMS 資料（登入憑證已失效）——"
              "專案查詢、SROI、圖表匯出、法規檢核都暫時無法使用。\n\n"
              "請回 CMS 重新點一次「進 AI 秘書」。在那之前，以下回答**不含**你的專案資料。",
        "en": "⚠️ I can't read your CMS data right now (your login credential has expired) — "
              "project queries, SROI, chart export and regulation check are temporarily unavailable.\n\n"
              "Please go back to the CMS and click \"AI Assistant\" again. Until then, answers below "
              "**do not** include your project data.",
        "ja": "⚠️ 現在 CMS のデータを読み取れません（ログイン資格情報の有効期限切れ）——"
              "プロジェクト照会、SROI、グラフ出力、法規チェックは一時的に利用できません。\n\n"
              "CMS に戻って「AI アシスタント」をもう一度クリックしてください。それまでの回答にはプロジェクトデータが**含まれません**。",
        "ko": "⚠️ 현재 CMS 데이터를 읽을 수 없습니다（로그인 자격 증명 만료）—— "
              "프로젝트 조회, SROI, 차트 내보내기, 법규 검토를 일시적으로 사용할 수 없습니다.\n\n"
              "CMS로 돌아가 \"AI 비서\"를 다시 클릭해 주세요. 그전까지 아래 답변에는 프로젝트 데이터가 **포함되지 않습니다**.",
    },
    "session.expired_attach": {
        "zh": "⚠️ 你的登入可能過期了，附件沒被處理。請重新從 CMS 點一次「進 AI 秘書」再上傳。",
        "en": "⚠️ Your login may have expired, so the attachment wasn't processed. Please click \"AI Assistant\" in the CMS again and re-upload.",
        "ja": "⚠️ ログインの有効期限が切れている可能性があり、添付ファイルは処理されませんでした。CMS から「AI アシスタント」をもう一度クリックして再アップロードしてください。",
        "ko": "⚠️ 로그인이 만료되어 첨부 파일이 처리되지 않았을 수 있습니다. CMS에서 \"AI 비서\"를 다시 클릭한 뒤 다시 업로드해 주세요.",
    },
    "device.dispatched": {
        "zh": "好，已請 {nodes} 處理（{count} 個動作），結果會傳到 LINE 👌",
        "en": "OK, I've asked {nodes} to handle it ({count} action(s)); results will be sent to LINE 👌",
        "ja": "了解、{nodes} に処理を依頼しました（{count} 件の操作）。結果は LINE に届きます 👌",
        "ko": "알겠습니다, {nodes}에 처리를 요청했습니다（{count}개 동작）. 결과는 LINE으로 전송됩니다 👌",
    },
    # 寫入確認
    "confirm.expired": {
        "zh": "這個確認已失效，請重新說一次需求。",
        "en": "This confirmation has expired. Please tell me your request again.",
        "ja": "この確認は無効になりました。もう一度ご要望をお伝えください。",
        "ko": "이 확인은 만료되었습니다. 요청을 다시 말씀해 주세요.",
    },
    "confirm.cancelled": {
        "zh": "好，已取消，沒有送出。",
        "en": "OK, cancelled — nothing was submitted.",
        "ja": "キャンセルしました。送信していません。",
        "ko": "취소했습니다. 전송하지 않았습니다.",
    },
    "confirm.auth_expired": {
        "zh": "⚠️ 登入授權已過期，這次沒有送出。請回 CMS 重新點一次「進 AI 秘書」後再確認。",
        "en": "⚠️ Your login has expired, so nothing was submitted. Please click \"AI Assistant\" in the CMS again, then confirm.",
        "ja": "⚠️ ログイン認証の有効期限が切れたため、送信していません。CMS から「AI アシスタント」をもう一度クリックしてから確認してください。",
        "ko": "⚠️ 로그인 인증이 만료되어 전송하지 않았습니다. CMS에서 \"AI 비서\"를 다시 클릭한 후 확인해 주세요.",
    },
    "confirm.failed": {
        "zh": "⚠️ 執行失敗（{err}）",
        "en": "⚠️ Execution failed ({err})",
        "ja": "⚠️ 実行に失敗しました（{err}）",
        "ko": "⚠️ 실행에 실패했습니다（{err}）",
    },
    # SDG / SROI
    "sdg.failed": {
        "zh": "（SDG 自動產生失敗，可稍後再說「幫我產 SDG」）",
        "en": "(Automatic SDG generation failed; you can say \"generate SDG\" later.)",
        "ja": "（SDG の自動生成に失敗しました。後で「SDG を作って」と言ってください）",
        "ko": "（SDG 자동 생성에 실패했습니다. 나중에 \"SDG 만들어 줘\"라고 말씀해 주세요）",
    },
    "sroi.offer": {
        "zh": "要不要順便產一版 **SROI 草稿**？會花一點時間，產完你可進試算表自己修。",
        "en": "Would you like me to draft an **SROI** as well? It takes a little while; you can edit it in the spreadsheet afterwards.",
        "ja": "ついでに **SROI 草案**も作成しますか？少し時間がかかります。作成後はスプレッドシートで編集できます。",
        "ko": "**SROI 초안**도 함께 만들까요? 시간이 조금 걸리며, 완성 후 스프레드시트에서 직접 수정할 수 있습니다.",
    },
    "sroi.skip": {
        "zh": "好，這次先不做 SROI；需要時再跟我說。",
        "en": "OK, skipping SROI this time; just ask when you need it.",
        "ja": "了解、今回は SROI を作成しません。必要なときに言ってください。",
        "ko": "알겠습니다, 이번에는 SROI를 건너뜁니다. 필요할 때 말씀해 주세요.",
    },
    "sroi.not_found": {
        "zh": "找不到要做 SROI 的專案，請重新說一次。",
        "en": "I can't find the project for the SROI. Please tell me again.",
        "ja": "SROI を作成するプロジェクトが見つかりません。もう一度お伝えください。",
        "ko": "SROI를 만들 프로젝트를 찾을 수 없습니다. 다시 말씀해 주세요.",
    },
    "sroi.start": {
        "zh": "好，開始估算 SROI 草稿…（會花一點時間，請稍候）",
        "en": "OK, estimating the SROI draft… (this takes a little while, please wait)",
        "ja": "SROI 草案の試算を開始します…（少し時間がかかります。お待ちください）",
        "ko": "SROI 초안 추정을 시작합니다…（시간이 조금 걸립니다. 잠시 기다려 주세요）",
    },
    "sroi.failed": {
        "zh": "⚠️ SROI 估算失敗（{err}）",
        "en": "⚠️ SROI estimation failed ({err})",
        "ja": "⚠️ SROI の試算に失敗しました（{err}）",
        "ko": "⚠️ SROI 추정에 실패했습니다（{err}）",
    },
    # 圖表
    "chart.no_permission": {
        "zh": "目前帳號沒有圖表資料權限。",
        "en": "This account has no permission for chart data.",
        "ja": "このアカウントにはグラフデータの権限がありません。",
        "ko": "이 계정에는 차트 데이터 권한이 없습니다.",
    },
    "chart.querying": {
        "zh": "⏳ 正在查詢圖表資料，請稍候…",
        "en": "⏳ Querying chart data, please wait…",
        "ja": "⏳ グラフデータを照会しています。お待ちください…",
        "ko": "⏳ 차트 데이터를 조회 중입니다. 잠시 기다려 주세요…",
    },
    "chart.query_error": {
        "zh": "查詢失敗：{err}",
        "en": "Query failed: {err}",
        "ja": "照会に失敗しました：{err}",
        "ko": "조회 실패: {err}",
    },
    "chart.query_failed": {
        "zh": "⚠️ 圖表查詢失敗，請稍後再試。",
        "en": "⚠️ Chart query failed, please try again later.",
        "ja": "⚠️ グラフの照会に失敗しました。後でもう一度お試しください。",
        "ko": "⚠️ 차트 조회에 실패했습니다. 잠시 후 다시 시도해 주세요.",
    },
    "chart.updated": {
        "zh": "✅ 圖表資料已更新。",
        "en": "✅ Chart data updated.",
        "ja": "✅ グラフデータを更新しました。",
        "ko": "✅ 차트 데이터가 업데이트되었습니다.",
    },
    "export.no_permission": {
        "zh": "⚠️ 目前帳號沒有圖表匯出權限。",
        "en": "⚠️ This account has no permission to export charts.",
        "ja": "⚠️ このアカウントにはグラフ出力の権限がありません。",
        "ko": "⚠️ 이 계정에는 차트 내보내기 권한이 없습니다.",
    },
    "export.generating": {
        "zh": "⏳ 正在產生 {fmt} 檔案，請稍候…",
        "en": "⏳ Generating the {fmt} file, please wait…",
        "ja": "⏳ {fmt} ファイルを生成しています。お待ちください…",
        "ko": "⏳ {fmt} 파일을 생성 중입니다. 잠시 기다려 주세요…",
    },
    "export.done": {
        "zh": "✅ 已匯出 {filename}。",
        "en": "✅ Exported {filename}.",
        "ja": "✅ {filename} を出力しました。",
        "ko": "✅ {filename}을(를) 내보냈습니다.",
    },
    "export.failed": {
        "zh": "⚠️ 圖表匯出失敗（{err}）。",
        "en": "⚠️ Chart export failed ({err}).",
        "ja": "⚠️ グラフの出力に失敗しました（{err}）。",
        "ko": "⚠️ 차트 내보내기에 실패했습니다（{err}）.",
    },
}

# 工具按鈕與歡迎訊息（驗收 (d) 必掃的鍵）
WELCOME_KEYS: tuple[str, ...] = ("welcome.sso", "welcome.no_tools", "welcome.guest")
BUTTON_KEYS: tuple[str, ...] = tuple(k for k in STRINGS if k.startswith("btn."))
