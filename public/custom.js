// #206：介面語系跟著 CMS 通行證的 lang 走。
// 後端 SSO handoff 會寫非 HttpOnly 的 eva_lang cookie（zh-TW / en-US / ja / ko），
// Chainlit 前端用 navigator.language 決定翻譯檔（.chainlit/translations/<locale>.json），
// 所以在 bundle 載入前（custom_js 是同步 <script>）覆寫 navigator.language(s)。
// 連線後若 session 語言與 cookie 不同（例如 refresh 後語言變了），後端送 window message
// {eva_lang}，這裡更新 cookie 並重新載入一次。
var EVA_LOCALES = ["zh-TW", "en-US", "ja", "ko"];
function evaLangCookie() {
  var m = document.cookie.match(/(?:^|;\s*)eva_lang=([^;]+)/);
  var v = m ? decodeURIComponent(m[1]) : "";
  return EVA_LOCALES.indexOf(v) >= 0 ? v : "";
}
(function () {
  var lang = evaLangCookie();
  if (!lang) return;
  try {
    Object.defineProperty(navigator, "language", { get: function () { return lang; }, configurable: true });
    Object.defineProperty(navigator, "languages", { get: function () { return [lang]; }, configurable: true });
  } catch (e) { console.warn("[eva] cannot override navigator.language", e); }
  try { document.documentElement.lang = lang; } catch (e) {}
})();
(function () {
  var reloaded = false;
  window.addEventListener("message", function (ev) {
    var data = ev && ev.data;
    if (!data || typeof data !== "object" || !data.eva_lang) return;
    var want = String(data.eva_lang);
    if (EVA_LOCALES.indexOf(want) < 0 || want === evaLangCookie() || reloaded) return;
    var secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = "eva_lang=" + encodeURIComponent(want) + "; path=/; max-age=28800; SameSite=Lax" + secure;
    reloaded = true;
    location.reload();
  });
})();

// #43／ai-eva#233：SSO 來源（帶 eva_sso_hint cookie）進站時，聊天室就緒前蓋一層品牌過場
// （logo＋「正在帶你到 AI 秘書…」，依語言），避免 Chainlit SPA 載入期間全白、或先閃登入表單。
// 外觀全在 custom.css（html.eva-handoff body::before/::after）：這支 JS 是 <head> 裡的同步 <script>，
// 這裡就把 class 掛上，<body> 一出現（React 還沒掛載）過場就在，不必等 DOMContentLoaded。
// 只在有 hint cookie 時動作 → 沒 session 的 standalone 訪客完全不受影響。
(function () {
  console.info("[eva] panel launcher loaded");
  // 用非 HttpOnly 的 eva_sso_hint 偵測（真正的 eva_sso 是 HttpOnly，JS 讀不到）。
  if (!/(^|;\s*)eva_sso_hint=/.test(document.cookie)) return;  // 非 SSO 來源 → 不蓋，standalone 照舊
  var root = document.documentElement;
  root.classList.add("eva-handoff");
  var done = false;
  function remove() {
    if (done) return;
    done = true;
    try { obs.disconnect(); } catch (e) {}
    root.classList.add("eva-handoff-out");   // 淡出（custom.css transition）
    setTimeout(function () { root.classList.remove("eva-handoff", "eva-handoff-out"); }, 350);
  }
  // 聊天室就緒 = 輸入框出現（登入頁沒有）且開場訊息已到；只有輸入框就再等一下，
  // 免得瞥見側邊欄／訊息還在 hydrate 的空殼。
  var inputAt = 0;
  function check() {
    if (!document.body) return;
    var input = document.querySelector('textarea, [contenteditable="true"]');
    if (!input) return;
    if (!inputAt) inputAt = Date.now();
    var msg = document.querySelector('[data-step-type], .step, .message-content, .prose');
    if (msg) setTimeout(remove, 200);
    else if (Date.now() - inputAt > 2500) remove();
  }
  var obs = new MutationObserver(check);
  function start() {
    obs.observe(document.body, { childList: true, subtree: true });
    check();
  }
  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
  // 輸入框出現但訊息遲遲不來時，MutationObserver 不一定再觸發 → 定時補看一次
  var tick = setInterval(function () { if (done) clearInterval(tick); else check(); }, 500);
  // 硬上限：8 秒一定移除（偵測失敗時不讓過場卡住）
  setTimeout(remove, 8000);
})();

// Chainlit selects commands without sending a message. Submit panel commands
// explicitly so each app can seed its flow.
// （原本這段寫在 SSO splash 的函式裡面，只有 SSO 來源才生效；#233 把 splash 拆出來，行為照舊。）
(function () {
  if (!/(^|;\s*)eva_sso_hint=/.test(document.cookie)) return;
  function visibleInput() {
    return Array.from(document.querySelectorAll("textarea, [contenteditable='true']")).find(function (node) {
      var rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && window.getComputedStyle(node).visibility !== "hidden";
    });
  }
  function submit(prompt) {
    var input = visibleInput();
    if (!input || (input.value || input.textContent || "").trim()) return;
    if (input.isContentEditable) {
      input.textContent = prompt;
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: prompt }));
    } else {
      var setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value").set;
      setter.call(input, prompt);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    }
    setTimeout(function () {
      input.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter", code: "Enter", keyCode: 13, which: 13,
        bubbles: true, cancelable: true,
      }));
      input.dispatchEvent(new KeyboardEvent("keyup", {
        key: "Enter", code: "Enter", keyCode: 13, which: 13,
        bubbles: true, cancelable: true,
      }));
    }, 80);
  }
  // 選單項目的文字長得像 "knowledge_base法規知識庫"（id + 標籤）。
  // 有分行就取最後一段，否則把開頭的英數 id 去掉，留人看得懂的標籤。
  function commandLabel(item) {
    var parts = (item.innerText || item.textContent || "")
      .split("\n").map(function (s) { return s.trim(); }).filter(Boolean);
    if (parts.length > 1) return parts[parts.length - 1];
    var t = parts[0] || "";
    var stripped = t.replace(/^[a-z0-9_.-]+/i, "").trim();
    return stripped || t;
  }

  function start() {
    document.addEventListener("click", function (event) {
      var item = event.target.closest('button, [role="menuitem"], [role="option"]');
      if (!item || item.id === "command-button" || item.closest("#command-button")) return;
      var popover = item.closest("#command-popover");
      if (!popover && !item.closest('[data-popover-content="true"]')) return;
      // 原本這裡寫死只認「圖表分析 / 社群貼文」，其他 app 一律不送出 ——
      // 於是從選單點新的工具（法規檢核、法規知識庫）就毫無反應，使用者以為壞掉。
      // 改成通用：把選到的那一項的標籤送出去即可，實際派工是看 msg.command，
      // 內容只是讓訊息非空、順便在對話裡留下「使用者點了什麼」的痕跡。
      var prompt = commandLabel(item);
      if (prompt) {
        setTimeout(function () { submit(prompt); }, 120);
      }
    }, true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

// 鎖定淺色主題。
//
// Chainlit 的主題偏好存在 localStorage['vite-ui-theme']（值 light / dark / system），
// 由 React 在啟動時讀取並在 <html> 掛上 dark class。custom.css 只是把切換鈕藏起來，
// 之前切過深色的使用者會卡在深色出不來 —— 所以這裡直接把偏好寫回 light，
// 並在啟動初期盯著 <html>，把殘留的 dark class 拿掉。
(function () {
  var KEY = "vite-ui-theme";
  try { localStorage.setItem(KEY, "light"); } catch (e) {}

  function forceLight() {
    var el = document.documentElement;
    if (el && el.classList.contains("dark")) {
      el.classList.remove("dark");
      el.classList.add("light");
    }
  }
  forceLight();

  // React 掛載後可能再套一次 dark，盯 8 秒就夠（之後使用者也切不了，按鈕已隱藏）
  var obs = new MutationObserver(forceLight);
  function start() {
    forceLight();
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    setTimeout(function () { try { obs.disconnect(); } catch (e) {} }, 8000);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();

// ai-eva#172：通用「返回來源網站」。由誰帶使用者進來（issuer）決定要不要顯示：
// issuer 在 handoff token 帶 return_url／return_label，後端驗過（https＋該 issuer 登記的網域）
// 才寫 eva_return cookie。沒有 cookie（直接使用 AI-Eva、或 issuer 沒帶）→ 什麼都不顯示。
(function () {
  function readReturn() {
    var m = document.cookie.match(/(?:^|;\s*)eva_return=([^;]+)/);
    if (!m) return null;
    try {
      var raw = decodeURIComponent(m[1]);
      if (raw.charAt(0) === '"') raw = JSON.parse(raw);
      var v = JSON.parse(raw);
      return v && typeof v.url === "string" && /^https:\/\//.test(v.url) ? v : null;
    } catch (e) { return null; }
  }
  var ret = readReturn();
  if (!ret) return;
  var LABEL = { "zh-TW": "\u8fd4\u56de", "en-US": "Back to", "ja": "\u623b\u308b\uff1a", "ko": "\ub3cc\uc544\uac00\uae30:" };  // 返回／戻る：／돌아가기:（escape：不依賴伺服器 charset）
  var prefix = LABEL[evaLangCookie()] || "\u8fd4\u56de";

  function mount() {
    if (document.getElementById("eva-return-link")) return true;
    var bar = document.querySelector("#header") || document.querySelector("header");
    if (!bar) return false;
    var a = document.createElement("a");
    a.id = "eva-return-link";
    a.href = ret.url;
    a.textContent = "\u2190 " + prefix + " " + (ret.label || "");
    a.setAttribute("aria-label", a.textContent);
    Object.assign(a.style, {
      display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
      marginRight: "8px", borderRadius: "999px", border: "1px solid rgba(0,0,0,.12)",
      font: "500 14px -apple-system, system-ui, 'Noto Sans TC', sans-serif",
      color: "inherit", textDecoration: "none", whiteSpace: "nowrap", background: "#fff",
    });
    var right = bar.lastElementChild || bar;
    right.insertBefore(a, right.firstChild);
    return true;
  }
  // Chainlit 是 SPA：頁首在 React 掛載後才出現，換頁也可能重畫 → 一直盯著，不見了就補回。
  var obs = new MutationObserver(function () { mount(); });
  function start() {
    mount();
    obs.observe(document.body, { childList: true, subtree: true });
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
