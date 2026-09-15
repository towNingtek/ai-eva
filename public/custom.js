// #43：SSO 來源（帶 eva_sso cookie）進站時，session 解析完成前蓋一層「登入中…」splash，
// 避免 Chainlit SPA 先 render 登入表單再切 chatroom 的那一閃。
// 只在有 eva_sso cookie 時動作 → 沒 session 的 standalone 訪客完全不受影響（照常看登入頁）。
(function () {
  console.info("[eva] panel launcher loaded");
  // 用非 HttpOnly 的 eva_sso_hint 偵測（真正的 eva_sso 是 HttpOnly，JS 讀不到）。
  if (!/(^|;\s*)eva_sso_hint=/.test(document.cookie)) return;  // 非 SSO 來源 → 不蓋，standalone 照舊

  var splash = document.createElement("div");
  splash.id = "eva-sso-splash";
  splash.textContent = "登入中…";
  Object.assign(splash.style, {
    position: "fixed", inset: "0", zIndex: "99999",
    display: "flex", alignItems: "center", justifyContent: "center",
    background: "#ffffff", color: "#555",
    font: "500 18px -apple-system, system-ui, 'Noto Sans TC', sans-serif",
    transition: "opacity .3s ease",
  });

  function mount() {
    if (document.body && !document.getElementById("eva-sso-splash")) {
      document.body.appendChild(splash);
    }
  }
  function remove() {
    splash.style.opacity = "0";
    setTimeout(function () { try { splash.remove(); } catch (e) {} }, 350);
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);

  // chatroom 出現（訊息輸入框 = textarea / contenteditable，登入頁沒有）→ 再等版面 settle
  // 才淡出。直接移除會瞥見側邊欄（過去7天/歷史）還在 hydrate 的那一閃。
  var obs = new MutationObserver(function () {
    if (document.querySelector('textarea, [contenteditable="true"]')) {
      obs.disconnect();
      setTimeout(remove, 500);  // 留時間給 sidebar/layout 畫完
    }
  });
  document.addEventListener("DOMContentLoaded", function () {
    mount();
    obs.observe(document.body, { childList: true, subtree: true });
  });

  // 硬上限：4 秒一定移除（偵測失敗時不讓 splash 卡住）
  setTimeout(function () { try { obs.disconnect(); } catch (e) {} remove(); }, 4000);

// Chainlit selects commands without sending a message. Submit panel commands
// explicitly so each app can seed its flow.
(function () {
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
