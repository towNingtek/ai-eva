// ai-eva#233 AI 秘書入口：真的 Chainlit 前端（chainlit run）＋真的 /sso/handoff（app/surfaces/sso.py）＋
// 真的 public/custom.css、custom.js、.chainlit/config.toml。只把「CMS 驗章／抓 manifest」換成假的（不連網），
// 開場訊息照 app/main.py 的 SSO 分支組：t("welcome.sso") ＋ 每個工具一顆 open_app 按鈕。
// (a) 手機 390×844、四語：開場訊息載入後，工具按鈕列至少一顆完整在第一屏，且沒被輸入框遮住
// (b) 從「CMS 頁」點 AI 秘書 → /sso/handoff → / → 聊天室就緒，每 0.3 秒截圖，沒有任何一張全白（白像素 > 98%）。
//     模擬實站延遲：驗章 1 秒、Chainlit 前端 bundle 晚 1.5 秒到。
// Python：$EVA_PYTHON → ~/.venvs/swarm-aieva/bin/python → python3（要裝 chainlit）。
// Playwright 由 NODE_PATH 提供（找不到時退回常用位置）。最後一行 PASS；任何失敗 exit 1。
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const {spawn, spawnSync} = require('node:child_process');

function loadPlaywright() {
  const tries = ['playwright', '/home/yillkid/workspace/swarm/hives/town-intelligent/e2e/node_modules/playwright',
    '/tmp/pw/node_modules/playwright'];
  for (const t of tries) { try { return require(t); } catch {} }
  console.error('Playwright not found. Set NODE_PATH to a node_modules that has playwright.'); process.exit(2);
}
const {chromium} = loadPlaywright();

const ROOT = path.resolve(__dirname, '../..');
const W = 390, H = 844, WHITE_LIMIT = 0.98, SHOT_EVERY = 300;
const LANGS = {zh: 'zh-TW', en: 'en-US', ja: 'ja', ko: 'ko'};

function findPython() {
  const c = [process.env.EVA_PYTHON, path.join(os.homedir(), '.venvs/swarm-aieva/bin/python'), 'python3', 'python'].filter(Boolean);
  for (const p of c) {
    const r = spawnSync(p, ['-c', 'import chainlit'], {stdio: 'ignore'});
    if (r.status === 0) return p;
  }
  console.error('FAIL no python with chainlit (set EVA_PYTHON)'); process.exit(1);
}

const APP_PY = `
import os, sys, time, json, base64
sys.path.insert(0, ${JSON.stringify(ROOT)})
os.environ.setdefault("CHAINLIT_AUTH_SECRET", "lab-233-" + "x" * 40)
os.environ["DATABASE_URL"] = ""
import chainlit as cl
from app.auth import issuers
from app.surfaces import sso   # 註冊真的 /sso/handoff
from app.i18n import t, app_label, normalize_lang
from app.apps._registry import menu_apps
from app.matching import invites as match_invites

def _claims(token):
    p = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))

def _verify(token):
    time.sleep(1.0)            # 模擬實站驗章＋JWKS 的延遲
    c = _claims(token)
    return {"issuer": "tplanet-cms", "project": "lab", "tenant_id": "lab", "user_id": 7,
            "email": "u@example.com", "lang": normalize_lang(c.get("lang")), "claims": c}

issuers.verify_handoff = _verify
issuers.fetch_manifest = lambda *a, **k: {"tools": []}
sso._DATABASE_URL = ""

TOOLS = ["dashboard_sdg_data", "dashboard_chart_query", "chart_export", "create_project", "list_my_projects",
         "get_project_info", "get_sroi", "get_sroi_template", "save_sroi", "save_sdg", "generate_sdg",
         "estimate_and_save_sroi", "generate_and_save_sdg"]
LOC2LANG = {"zh-TW": "zh", "en-US": "en", "ja": "ja", "ko": "ko"}

@cl.on_chat_start
async def start():
    cookie = (cl.context.session.environ or {}).get("HTTP_COOKIE", "")
    lang = "zh"
    for part in cookie.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "eva_lang":
            lang = LOC2LANG.get(v, "zh")
    actions = [cl.Action(name="open_app", payload={"app": a.id},
                         label=f"{a.icon} {app_label(a.id, a.label, lang=lang)}".replace("\\ufe0f", ""))
               for a in menu_apps()]
    # 照舊版 main.py 也給 tools=（13 個 manifest 工具名）：模板若還列程式名，(a) 會量到被推出第一屏
    content = t("welcome.sso", lang=lang, who="u@example.com", tools=", ".join(TOOLS))
    if "eva_lab_invites=1" in cookie:
        # 照 main.py：有未回覆媒合邀請時，提醒放在開場最前面＋多一顆「看邀請」按鈕（實站最長的開場）
        invs = [{"project": n, "created_at": "2026-11-2" + str(i), "status": "pending"}
                for i, n in enumerate(["雲林縣海口淨灘與社區共餐計畫", "斗六青年返鄉創業陪伴計畫", "南投竹山長者共餐據點"])]
        content = match_invites.format_reminder(invs, lang) + "\\n\\n---\\n\\n" + content
        actions = [cl.Action(name=match_invites.ACTION_NAME, payload={"lang": lang},
                             label=match_invites.text("action", lang))] + actions
    await cl.Message(content=content, actions=actions).send()
`;

function freePort() {
  return new Promise(r => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => r(p)); }); });
}

async function waitHttp(url, ms) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    try { const r = await fetch(url); if (r.ok) return; } catch {}
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error('chainlit did not start: ' + url);
}

const b64u = s => Buffer.from(s).toString('base64').replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
const fakeToken = lang => `${b64u('{"alg":"none","typ":"JWT"}')}.${b64u(JSON.stringify({lang, aud: 'ai-eva'}))}.c2ln`;

let fails = 0;
const fail = m => { fails++; console.log('FAIL', m); };

(async () => {
  const py = findPython();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'eva233-'));
  const appFile = path.join(tmp, 'lab_app.py');
  fs.writeFileSync(appFile, APP_PY);
  const port = await freePort();
  const base = `http://localhost:${port}`;
  const chainlitBin = path.join(path.dirname(py), 'chainlit');
  const cmd = fs.existsSync(chainlitBin) ? [chainlitBin, ['run', appFile, '--headless', '--port', String(port), '--host', '127.0.0.1']]
    : [py, ['-m', 'chainlit', 'run', appFile, '--headless', '--port', String(port), '--host', '127.0.0.1']];
  const srv = spawn(cmd[0], cmd[1], {cwd: ROOT, env: {...process.env, PYTHONPATH: ROOT}, stdio: ['ignore', 'pipe', 'pipe']});
  let srvLog = '';
  srv.stdout.on('data', d => srvLog += d); srv.stderr.on('data', d => srvLog += d);
  const browser = await chromium.launch();
  try {
    await waitHttp(`${base}/public/custom.css`, 60000);

    // 不連外網：Google Fonts／KaTeX CDN 直接擋掉（實站載得到，這裡不讓它卡 render）
    const offline = async ctx => {
      await ctx.route(u => !/^https?:\/\/(localhost|127\.0\.0\.1)[:/]/.test(u.toString()), r => r.abort());
    };

    // ── (a) 手機開場：工具按鈕在第一屏且沒被輸入框遮住 ──────────────────────
    for (const [lang, invites] of Object.keys(LANGS).flatMap(l => [[l, false], [l, true]])) {
      const tag = `${lang}${invites ? '+invites' : ''}`;
      const ctx = await browser.newContext({viewport: {width: W, height: H}, isMobile: true, hasTouch: true, deviceScaleFactor: 2});
      await offline(ctx);
      if (invites) await ctx.addCookies([{name: 'eva_lab_invites', value: '1', url: base}]);
      const page = await ctx.newPage();
      await page.goto(`${base}/sso/handoff?token=${fakeToken(lang)}`);
      let res;
      try {
        await page.waitForFunction(() => !document.documentElement.classList.contains('eva-handoff')
          && [...document.querySelectorAll('button')].some(b => /📊|🔍|📚/.test(b.textContent)), null, {timeout: 20000});
        await page.waitForTimeout(800);   // 讓自動捲動／版面 settle
        res = await page.evaluate(([W, H]) => {
          const input = document.querySelector('textarea, [contenteditable="true"]');
          let comp = input;
          // 往上找輸入框外框（含附件／送出鈕的那一整塊）：寬度接近整列的最外層、但不是整頁
          for (let n = input; n && n !== document.body; n = n.parentElement) {
            const r = n.getBoundingClientRect();
            if (r.height > H * 0.5) break;
            comp = n;
          }
          const cr = comp.getBoundingClientRect();
          const btns = [...document.querySelectorAll('button')].filter(b => /^\s*(📊|🪞|📚|🧭|🤝|⚖|📣|🔍)/.test(b.textContent));
          const ok = btns.filter(b => {
            const r = b.getBoundingClientRect();
            if (!(r.width > 0 && r.top >= 0 && r.left >= 0 && r.bottom <= H && r.right <= W)) return false;
            if (r.bottom > cr.top && r.top < cr.bottom) return false;   // 跟輸入框重疊
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return hit && (hit === b || b.contains(hit));
          });
          // 開場訊息的開頭（問候那一行，含 who）也要在同一屏：整段開場不佔滿一屏
          const greet = [...document.querySelectorAll('p, li, div')].filter(e => e.textContent.includes('u@example.com'))
            .sort((a, b) => a.textContent.length - b.textContent.length)[0];
          const gr = greet ? greet.getBoundingClientRect() : null;
          return {buttons: btns.length, ok: ok.map(b => b.textContent.trim()), composerTop: Math.round(cr.top),
            greetTop: gr ? Math.round(gr.top) : null,
            first: btns[0] ? JSON.stringify(btns[0].getBoundingClientRect()) : null};
        }, [W, H]);
      } catch (e) { res = {error: e.message}; }
      await page.screenshot({path: path.join(tmp, `a-${tag}.png`)});
      if (res.error) fail(`(a) ${tag}: welcome not loaded: ${res.error}`);
      else if (!res.buttons) fail(`(a) ${tag}: no tool buttons`);
      else if (!res.ok.length) fail(`(a) ${tag}: no tool button fully on first screen above composer (composerTop=${res.composerTop}, first=${res.first})`);
      else if (res.greetTop === null || res.greetTop < 0) fail(`(a) ${tag}: welcome greeting scrolled off the first screen (top=${res.greetTop}): welcome takes more than one screen`);
      else console.log(`ok (a) ${tag}: ${res.ok.length}/${res.buttons} tool buttons on first screen, greeting top ${res.greetTop}, composer top ${res.composerTop}`);
      await ctx.close();
    }

    // ── (b) handoff 過場：每 0.3 秒截圖，不能有全白 ─────────────────────────
    const judge = await browser.newPage();
    const whiteRatio = async buf => judge.evaluate(async b64 => {
      const img = new Image(); img.src = 'data:image/png;base64,' + b64; await img.decode();
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
      const g = c.getContext('2d'); g.drawImage(img, 0, 0);
      const d = g.getImageData(0, 0, c.width, c.height).data; let w = 0;
      for (let i = 0; i < d.length; i += 4) if (d[i] >= 245 && d[i + 1] >= 245 && d[i + 2] >= 245) w++;
      return w / (d.length / 4);
    }, buf.toString('base64'));

    for (const [lang] of Object.entries(LANGS)) {
      const before = fails;
      const ctx = await browser.newContext({viewport: {width: W, height: H}, isMobile: true, hasTouch: true});
      await offline(ctx);
      // 模擬實站：Chainlit 前端 bundle 晚 1.5 秒到
      await ctx.route(/\/assets\/.*\.js$/, async r => { await new Promise(x => setTimeout(x, 1500)); r.continue(); });
      const page = await ctx.newPage();
      // CMS 頁（非白底）上的 AI 秘書連結
      await page.setContent(`<body style="margin:0;background:#2b3a4a;color:#fff;font:20px sans-serif">
        <div style="padding:40px">CMS</div><a id="go" style="color:#fff;font-size:24px;padding:40px;display:block"
        href="${base}/sso/handoff?token=${fakeToken(lang)}">AI 秘書</a></body>`);
      const shots = [];
      let stop = false, sawBrand = false;
      const t0 = Date.now();
      const loop = (async () => {
        let n = 0;
        while (!stop && Date.now() - t0 < 25000) {
          const due = t0 + n * SHOT_EVERY; const wait = due - Date.now();
          if (wait > 0) await new Promise(r => setTimeout(r, wait));
          try {
            const buf = await page.screenshot({timeout: 2000, animations: 'allow'});
            shots.push({t: Date.now() - t0, buf});
          } catch {}
          n++;
        }
      })();
      await page.click('#go');
      try {
        await page.waitForFunction(() => !document.documentElement.classList.contains('eva-handoff')
          && [...document.querySelectorAll('button')].some(b => /📊|🔍|📚/.test(b.textContent)), null, {timeout: 20000, polling: 100});
        await page.waitForTimeout(600);
      } catch (e) { fail(`(b) ${lang}: chat never became ready: ${e.message}`); }
      stop = true; await loop;
      if (shots.length < 5) fail(`(b) ${lang}: only ${shots.length} screenshots`);
      let worst = 0;
      for (const [i, s] of shots.entries()) {
        const r = await whiteRatio(s.buf);
        worst = Math.max(worst, r);
        if (r > WHITE_LIMIT) {
          const f = path.join(tmp, `b-${lang}-${i}.png`); fs.writeFileSync(f, s.buf);
          fail(`(b) ${lang}: screenshot #${i} at ${s.t}ms is ${(r * 100).toFixed(1)}% white (${f})`);
        }
        if (r < 0.5) sawBrand = true;
      }
      if (!sawBrand) fail(`(b) ${lang}: never saw the brand transition`);
      if (fails === before) console.log(`ok (b) ${lang}: ${shots.length} screenshots over ${shots.at(-1)?.t}ms, whitest ${(worst * 100).toFixed(1)}%`);
      await ctx.close();
    }
  } catch (e) {
    fail(e.stack || e.message);
    console.log(srvLog.slice(-3000));
  } finally {
    await browser.close();
    srv.kill('SIGTERM');
  }
  if (fails) { console.log(`FAILED ${fails} (artifacts: ${tmp})`); process.exit(1); }
  console.log('PASS');
  process.exit(0);
})();
