// AI Eva: + expandable menu (currently: 附加檔案)
(function () {
  const TAG = "[ai-eva:+menu]";
  let wired = false;
  let plusBtn, menu, lastAttachBtn;

  function log(...args) {
    try {
      console.log(TAG, ...args);
    } catch (e) {}
  }

  function findAttachButton() {
    // Hidden file input exists near the attach button
    const fileInput = document.querySelector('input[type="file"]');
    if (fileInput) {
      // Walk up to form/container, then find the trigger button
      let parent = fileInput.parentElement;
      for (let i = 0; i < 6 && parent; i++) {
        const btn = parent.querySelector("button");
        if (btn) return btn;
        parent = parent.parentElement;
      }
    }

    // Try aria-label / title
    const selectors = [
      'button[aria-label*="attach" i]',
      'button[aria-label*="upload" i]',
      'button[aria-label*="附加" i]',
      'button[aria-label*="上傳" i]',
      'button[title*="attach" i]',
      'button[title*="upload" i]',
    ];
    for (const sel of selectors) {
      const btn = document.querySelector(sel);
      if (btn) return btn;
    }

    // SVG heuristic: look for an svg whose class or data contains "paperclip" or similar
    const svgs = document.querySelectorAll("button svg");
    for (const svg of svgs) {
      const cls = (svg.getAttribute("class") || "").toLowerCase();
      if (cls.includes("paperclip") || cls.includes("attach") || cls.includes("clip")) {
        return svg.closest("button");
      }
    }

    return null;
  }

  function buildMenu(attachBtn) {
    const m = document.createElement("div");
    m.className = "eva-tool-menu";
    m.style.display = "none";
    m.innerHTML = `
      <button type="button" class="eva-tool-item" data-action="attach">
        <span class="eva-icon">📎</span><span>附加檔案</span>
      </button>
    `;
    document.body.appendChild(m);
    m.addEventListener("click", (e) => {
      e.stopPropagation();
      const item = e.target.closest(".eva-tool-item");
      if (!item) return;
      if (item.dataset.action === "attach") {
        if (lastAttachBtn) lastAttachBtn.click();
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

  function showMenu() {
    positionMenu();
    menu.style.display = "block";
    plusBtn.classList.add("open");
  }

  function hideMenu() {
    if (!menu) return;
    menu.style.display = "none";
    if (plusBtn) plusBtn.classList.remove("open");
  }

  function setup() {
    if (wired && plusBtn && document.contains(plusBtn)) return;
    const attachBtn = findAttachButton();
    if (!attachBtn) {
      log("waiting for attach button...");
      return false;
    }
    log("found attach button:", attachBtn);

    // Clean up old
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
    menu = buildMenu(attachBtn);

    plusBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (menu.style.display === "block") hideMenu();
      else showMenu();
    });

    document.addEventListener("click", hideMenu);
    window.addEventListener("resize", () => {
      if (menu.style.display === "block") positionMenu();
    });

    wired = true;
    log("✅ wired");
    return true;
  }

  // Try every 500ms until mounted
  const interval = setInterval(() => {
    if (setup()) clearInterval(interval);
  }, 500);

  // Also observe (SPA re-renders can remove our button)
  const observer = new MutationObserver(() => {
    if (!wired || !plusBtn || !document.contains(plusBtn)) {
      wired = false;
      setup();
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
