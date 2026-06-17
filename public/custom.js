// #43：SSO 來源（帶 eva_sso cookie）進站時，session 解析完成前蓋一層「登入中…」splash，
// 避免 Chainlit SPA 先 render 登入表單再切 chatroom 的那一閃。
// 只在有 eva_sso cookie 時動作 → 沒 session 的 standalone 訪客完全不受影響（照常看登入頁）。
(function () {
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
})();
