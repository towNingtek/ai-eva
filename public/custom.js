// AI Eva: + expandable menu + "mode" pill (hides trigger prefix from UI)
(function () {
  const TAG = "[ai-eva:+menu]";
  const MODE_PILL_ID = "eva-mode-pill";
  let wired = false;
  let wiring = false;
  let plusBtn, menu, lastAttachBtn;
  let appsCache = null;
  let activeMode = null;     // {id, trigger, label, icon}
  let injectingSubmit = false; // re-entrancy guard for programmatic submit

  const log = (...a) => { try { console.log(TAG, ...a); } catch {} };

  async function loadApps() {
    if (appsCache) return appsCache;
    try {
      const r = await fetch("/public/apps.json", { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status);
      const data = await r.json();
      appsCache = Array.isArray(data.apps) ? data.apps : [];
    } catch (e) {
      log("apps.json load failed:", e);
      appsCache = [];
    }
    return appsCache;
  }

  function findAttachButton() {
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      let p = fileInput.parentElement;
      for (let i = 0; i < 6 && p; i++) {
        const btn = p.querySelector("button");
        if (btn) return btn;
        p = p.parentElement;
      }
    }
    for (const sel of ['button[aria-label*="attach" i]','button[aria-label*="upload" i]','button[aria-label*="附加" i]','button[aria-label*="上傳" i]']) {
      const btn = document.querySelector(sel);
      if (btn) return btn;
    }
    return null;
  }

  function findChatTextarea() {
    return (
      document.querySelector('textarea[data-test="chat-input"]') ||
      document.querySelector('#chat-input textarea') ||
      document.querySelector('form textarea') ||
      document.querySelector('textarea')
    );
  }

  function findSendButton() {
    // Prefer send icon button next to textarea
    const ta = findChatTextarea();
    if (ta) {
      const form = ta.closest("form");
      if (form) {
        const btns = form.querySelectorAll("button");
        // Usually the last button in the input form is Send
        for (let i = btns.length - 1; i >= 0; i--) {
          const b = btns[i];
          const label = (b.getAttribute("aria-label") || "").toLowerCase();
          if (label.includes("send") || label.includes("送出") || label.includes("submit")) return b;
        }
        if (btns.length) return btns[btns.length - 1];
      }
    }
    return (
      document.querySelector('button[aria-label*="send" i]') ||
      document.querySelector('button[type="submit"]')
    );
  }

  function setTextareaValue(ta, value) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
    setter.call(ta, value);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  }

  // ----- Mode pill -----
  function getPill() {
    let pill = document.getElementById(MODE_PILL_ID);
    if (pill) return pill;
    pill = document.createElement("div");
    pill.id = MODE_PILL_ID;
    pill.className = "eva-mode-pill";
    pill.style.display = "none";
    pill.innerHTML = `
      <span class="eva-mode-icon"></span>
      <span class="eva-mode-label"></span>
      <button type="button" class="eva-mode-close" aria-label="取消模式">×</button>
    `;
    document.body.appendChild(pill);
    pill.querySelector(".eva-mode-close").addEventListener("click", (e) => {
      e.stopPropagation();
      clearMode();
    });
    return pill;
  }

  function positionPill() {
    const pill = getPill();
    const ta = findChatTextarea();
    if (!pill || !ta || pill.style.display === "none") return;
    const r = ta.getBoundingClientRect();
    pill.style.left = r.left + "px";
    pill.style.top = Math.max(8, r.top - pill.offsetHeight - 8) + "px";
  }

  function setMode(mode) {
    activeMode = mode;
    const pill = getPill();
    pill.querySelector(".eva-mode-icon").textContent = mode.icon || "🔧";
    pill.querySelector(".eva-mode-label").textContent = mode.label || "";
    pill.style.display = "flex";
    positionPill();
    const ta = findChatTextarea();
    if (ta) ta.focus();
  }

  function clearMode() {
    activeMode = null;
    const pill = document.getElementById(MODE_PILL_ID);
    if (pill) pill.style.display = "none";
  }

  // ----- Intercept submit -----
  function trySubmitWithTrigger() {
    if (!activeMode) return false;
    const ta = findChatTextarea();
    if (!ta) return false;
    const val = (ta.value || "").trim();
    if (!val) return false;
    const trigger = activeMode.trigger;
    const prefixed = val.startsWith(trigger) ? val : `${trigger} ${val}`;
    setTextareaValue(ta, prefixed);
    // Let React pick up the state, then click send programmatically.
    // Mode persists until user clicks × on the pill — every subsequent
    // message keeps getting the trigger injected.
    setTimeout(() => {
      injectingSubmit = true;
      try {
        const btn = findSendButton();
        if (btn && !btn.disabled) {
          btn.click();
        } else {
          ta.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        }
      } finally {
        setTimeout(() => { injectingSubmit = false; }, 100);
      }
    }, 60);
    return true;
  }

  function installInterceptors() {
    // Enter key
    document.addEventListener("keydown", (e) => {
      if (!activeMode || injectingSubmit) return;
      if (e.key !== "Enter" || e.shiftKey || e.isComposing) return;
      const ta = e.target;
      if (!ta || ta.tagName !== "TEXTAREA") return;
      if (!(ta.value || "").trim()) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      trySubmitWithTrigger();
    }, true);

    // Send button click
    document.addEventListener("click", (e) => {
      if (!activeMode || injectingSubmit) return;
      const btn = e.target.closest("button");
      if (!btn) return;
      if (btn.closest(".eva-tool-menu")) return;
      if (btn.closest("#" + MODE_PILL_ID)) return;
      if (btn === plusBtn) return;
      const send = findSendButton();
      if (!send || btn !== send) return;
      const ta = findChatTextarea();
      if (!ta || !(ta.value || "").trim()) return;
      e.preventDefault();
      e.stopPropagation();
      e.stopImmediatePropagation();
      trySubmitWithTrigger();
    }, true);

    window.addEventListener("resize", positionPill);
    window.addEventListener("scroll", positionPill, true);
  }
  installInterceptors();

  // ----- Menu -----
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;" }[c]));
  }

  function buildMenu(apps) {
    const m = document.createElement("div");
    m.className = "eva-tool-menu";
    m.style.display = "none";

    const rows = [];
    rows.push(`
      <button type="button" class="eva-tool-item" data-action="attach">
        <span class="eva-icon">📎</span>
        <span class="eva-label-wrap"><span class="eva-label">附加檔案</span></span>
      </button>
    `);
    for (const a of apps) {
      const dis = a.enabled === false ? "eva-disabled" : "";
      const desc = a.description ? `<span class="eva-desc">${escapeHtml(a.description)}</span>` : "";
      rows.push(`
        <button type="button" class="eva-tool-item ${dis}" data-action="app" data-app-id="${escapeHtml(a.id)}" ${dis ? "disabled" : ""}>
          <span class="eva-icon">${escapeHtml(a.icon || "🔧")}</span>
          <span class="eva-label-wrap">
            <span class="eva-label">${escapeHtml(a.label || a.id)}</span>
            ${desc}
          </span>
        </button>
      `);
    }
    m.innerHTML = rows.join("");
    document.body.appendChild(m);

    m.addEventListener("click", (e) => {
      e.stopPropagation();
      const item = e.target.closest(".eva-tool-item");
      if (!item || item.classList.contains("eva-disabled")) return;
      const action = item.dataset.action;
      if (action === "attach" && lastAttachBtn) {
        lastAttachBtn.click();
      } else if (action === "app") {
        const id = item.dataset.appId;
        const app = (appsCache || []).find(a => a.id === id);
        if (app && app.trigger) {
          setMode({ id: app.id, trigger: app.trigger, label: app.label, icon: app.icon });
        }
      }
      hideMenu();
    });
    return m;
  }

  function positionMenu() {
    const r = plusBtn.getBoundingClientRect();
    menu.style.left = r.left + "px";
    menu.style.bottom = window.innerHeight - r.top + 8 + "px";
  }
  function showMenu() { positionMenu(); menu.style.display = "block"; plusBtn.classList.add("open"); }
  function hideMenu() { if (!menu) return; menu.style.display = "none"; if (plusBtn) plusBtn.classList.remove("open"); }

  async function setup() {
    if (wiring) return false;
    if (wired && plusBtn && document.contains(plusBtn)) return true;
    const attachBtn = findAttachButton();
    if (!attachBtn) return false;

    wiring = true;
    try {
      if (plusBtn && plusBtn.parentElement) plusBtn.remove();
      if (menu && menu.parentElement) menu.remove();

      lastAttachBtn = attachBtn;
      attachBtn.setAttribute("data-eva-hide-original", "1");

      plusBtn = document.createElement("button");
      plusBtn.type = "button";
      plusBtn.className = "eva-plus-btn";
      plusBtn.textContent = "+";
      plusBtn.setAttribute("aria-label", "工具");
      attachBtn.parentNode.insertBefore(plusBtn, attachBtn);

      const apps = await loadApps();
      menu = buildMenu(apps);
      log("✅ wired with", apps.length, "app(s):", apps.map(a => a.id));

      plusBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (menu.style.display === "block") hideMenu();
        else showMenu();
      });
      document.addEventListener("click", hideMenu);
      window.addEventListener("resize", () => { if (menu.style.display === "block") positionMenu(); });

      wired = true;
      return true;
    } finally {
      wiring = false;
    }
  }

  setup();
  setInterval(() => {
    if (!wired || !plusBtn || !document.contains(plusBtn)) {
      wired = false;
      setup();
    }
    // 若 textarea 重新 mount，pill 位置要重算
    positionPill();
  }, 2000);
})();
