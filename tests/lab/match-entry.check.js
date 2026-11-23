// ai-eva#237 媒合入口：真的 Chainlit 前端（chainlit run）＋真的 /sso/handoff（app/surfaces/sso.py）＋
// 真的 public/custom.css、tangle-lab-overlay.js（工作區外框）、embed.html＋match-task.js（媒合面板）＋
// 真的 app/apps/match_analysis/task.py（open_task → 清單 → 預選 A → CopilotFunction tangle_workspace）。
// 只把「CMS 驗章／抓 manifest／CMS 工具」換成假的（不連網）。開場照 app/main.py 的 SSO 分支：
// 工具按鈕依 menu_apps() 順序，按鈕 id＝eva-app-<app_id>-…（同 main._action_id），接著讀 eva_open cookie 自動開啟。
// (1) 第一顆工具按鈕是「尋找媒合夥伴」且有「新」徽章（::after）
// (2) 最後一顆是舊版「即將下線」，外觀弱化（虛線框或灰字）
// (3) /sso/handoff?open=match_analysis&a=<uuid> 進來：不點任何東西，媒合工作區就出現，A 已選好；
//     a 不在可發起清單 → 工作區照開但 A 不預選（停在下拉預設的第一個）；重整（同一 cookie）不再自動開。
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
const A_OK = 'aaaa1111-0000-4000-8000-000000000001';      // 本站可發起
const A_MINE = 'bbbb2222-0000-4000-8000-000000000002';    // 我的案，但本站不可發起
const A_FIRST = 'ffff0000-0000-4000-8000-000000000000';   // 可發起清單第一個（下拉預設值，沒預選時就是它）

function findPython() {
  const c = [process.env.EVA_PYTHON, path.join(os.homedir(), '.venvs/swarm-aieva/bin/python'), 'python3', 'python'].filter(Boolean);
  for (const p of c) {
    const r = spawnSync(p, ['-c', 'import chainlit'], {stdio: 'ignore'});
    if (r.status === 0) return p;
  }
  console.error('FAIL no python with chainlit (set EVA_PYTHON)'); process.exit(1);
}

const appPy = taskDir => `
import os, sys, json, base64
from uuid import uuid4
sys.path.insert(0, ${JSON.stringify(ROOT)})
os.environ.setdefault("CHAINLIT_AUTH_SECRET", "lab-237-" + "x" * 40)
os.environ["DATABASE_URL"] = ""
os.environ["TANGLE_LAW_TASK"] = "1"          # 有載 overlay 的部署（同 app/main.py）
os.environ["MATCH_TASK_PROJECTS"] = "lab"    # 這個租戶開星球媒合
import chainlit as cl
from chainlit.config import config as chainlit_config
from app.auth import issuers
from app.surfaces import sso   # 註冊真的 /sso/handoff
from app.i18n import t, app_label, normalize_lang
from app.apps._registry import menu_apps
from app.apps.match_analysis import task as match_task

# 同 app/main.py（TANGLE_LAW_TASK）：前端載入工作區外框（它會再載 custom.js）
chainlit_config.ui.custom_js = "/public/tangle-lab-overlay.js?v=law-task-2"
match_task.TASK_DIR = __import__("pathlib").Path(${JSON.stringify(taskDir)})

def _claims(token):
    p = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))

def _verify(token):
    c = _claims(token)
    return {"issuer": "tplanet-cms", "project": "lab", "tenant_id": "lab", "user_id": 7,
            "email": "u@example.com", "lang": normalize_lang(c.get("lang")), "claims": c}

issuers.verify_handoff = _verify
issuers.fetch_manifest = lambda *a, **k: {"tools": []}
sso._DATABASE_URL = ""

A_OK, A_MINE = ${JSON.stringify(A_OK)}, ${JSON.stringify(A_MINE)}
A_FIRST = ${JSON.stringify(A_FIRST)}
NAMES = {A_FIRST: "第一個可發起案", A_OK: "大庄社區", "cccc": "農產合作社", A_MINE: "青年團隊"}
INITIABLE = [A_FIRST, A_OK]   # A_OK 排第二：面板預設選第一個，選到 A_OK 才代表真的預選

class FakeCMS:
    def is_allowed(self, name):
        return True
    async def execute(self, name, args, confirmed=False):
        if name == "list_match_initiable_projects":
            return {"status": "ok", "result": {"data": {"count": len(INITIABLE), "items": [{"uuid": u, "name": NAMES[u]} for u in INITIABLE]}}}
        if name == "list_my_projects":
            return {"status": "ok", "result": {"data": {"projects": [{"uuid": u, "name": n} for u, n in NAMES.items()]}}}
        return {"status": "ok", "result": {"data": {"name": NAMES.get(args.get("uuid"), "?"), "philosophy": ""}}}

def _action_id(a):   # 同 app/main.py _action_id（tests/test_match_entry.py 驗 main 用同一格式）
    return f"eva-app-{a.id}-{uuid4().hex[:8]}"

@cl.on_chat_start
async def start():
    cookie = (cl.context.session.environ or {}).get("HTTP_COOKIE", "")
    actions = [cl.Action(name="open_app", payload={"app": a.id}, id=_action_id(a),
                         label=f"{a.icon} {app_label(a.id, a.label, lang='zh')}".replace("\\ufe0f", ""))
               for a in menu_apps()]
    await cl.Message(content=t("welcome.sso", lang="zh", who="u@example.com", tools=""), actions=actions).send()
    # 同 app/main.py _auto_open_from_cookie → _open_app_by_id（把 a 放進 session）→ match_analysis.task.open_from_tool
    intent = sso.consume_open(cookie)
    if not intent:
        return
    assert intent["app"] == "match_analysis", intent
    cl.user_session.set("cms_runtime", FakeCMS())
    cl.user_session.set("law_task_identity", {"issuer": "tplanet-cms", "project": "lab", "user_id": 7})
    cl.user_session.set(match_task.PRESELECT_KEY, intent.get("a"))
    assert await match_task.open_from_tool(), "match task did not open"

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
const ok = m => console.log('ok', m);

(async () => {
  const py = findPython();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'eva237-'));
  const appFile = path.join(tmp, 'lab_app.py');
  fs.writeFileSync(appFile, appPy(path.join(tmp, 'tasks')));
  const port = await freePort();
  const base = `http://localhost:${port}`;
  const chainlitBin = path.join(path.dirname(py), 'chainlit');
  const cmd = fs.existsSync(chainlitBin) ? [chainlitBin, ['run', appFile, '--headless', '--port', String(port), '--host', '127.0.0.1']]
    : [py, ['-m', 'chainlit', 'run', appFile, '--headless', '--port', String(port), '--host', '127.0.0.1']];
  const srv = spawn(cmd[0], cmd[1], {cwd: ROOT, env: {...process.env, PYTHONPATH: ROOT}, stdio: ['ignore', 'pipe', 'pipe']});
  let srvLog = '';
  srv.stdout.on('data', d => srvLog += d); srv.stderr.on('data', d => srvLog += d);
  const browser = await chromium.launch();
  const offline = async ctx => {
    await ctx.route(u => !/^https?:\/\/(localhost|127\.0\.0\.1)[:/]/.test(u.toString()), r => r.abort());
  };
  const toolButtons = page => page.evaluate(() => [...document.querySelectorAll('button[id^="eva-app-"]')].map(b => {
    const cs = getComputedStyle(b), after = getComputedStyle(b, '::after');
    return {id: b.id, text: b.textContent.trim(), after: after.content, border: cs.borderTopStyle, color: cs.color,
      opacity: Number(cs.opacity)};
  }));
  const waitWelcome = page => page.waitForFunction(() => !document.documentElement.classList.contains('eva-handoff')
    && document.querySelectorAll('button[id^="eva-app-"]').length > 1, null, {timeout: 30000});
  const wsOpen = page => page.evaluate(() => {
    const ws = document.getElementById('tangle-ws');
    return !!ws && !ws.classList.contains('hide') && getComputedStyle(ws).display !== 'none';
  });
  const matchFrame = page => page.frames().find(f => /embed\.html\?.*mode=match/.test(f.url()));

  try {
    await waitHttp(`${base}/public/custom.css`, 60000);

    // ── (1)(2) 工具列：新版第一＋「新」徽章；舊版最後＋弱化 ───────────────
    {
      const ctx = await browser.newContext({viewport: {width: 1280, height: 900}});
      await offline(ctx);
      const page = await ctx.newPage();
      await page.goto(`${base}/sso/handoff?token=${fakeToken('zh-TW')}`);
      await waitWelcome(page);
      await page.waitForTimeout(500);
      const btns = await toolButtons(page);
      const first = btns[0], last = btns.at(-1);
      if (!/^eva-app-match_analysis-/.test(first.id) || !first.text.includes('尋找媒合夥伴')) fail(`(1) first button is ${JSON.stringify(first)}`);
      else if (first.after !== '"新"') fail(`(1) first button badge ::after content=${first.after}`);
      else ok(`(1) first tool button 「${first.text}」 with badge ${first.after}`);
      const grey = (() => { const m = last.color.match(/\d+/g) || []; const [r, g, b] = m.map(Number);
        return Math.max(r, g, b) - Math.min(r, g, b) < 16 && r > 90; })();
      if (!/^eva-app-project_match-/.test(last.id) || !last.text.includes('舊版媒合（即將下線）')) fail(`(2) last button is ${JSON.stringify(last)}`);
      else if (!(last.border === 'dashed' || grey)) fail(`(2) legacy button not weakened: border=${last.border} color=${last.color}`);
      else ok(`(2) last tool button 「${last.text}」 weakened (border ${last.border}, color ${last.color}, opacity ${last.opacity})`);
      if (btns.filter(b => /^eva-app-project_match-/.test(b.id)).length !== 1) fail('(2) legacy button must stay (exactly once)');
      if (await wsOpen(page)) fail('(1) workspace opened without open=');
      await page.screenshot({path: path.join(tmp, 'toolbar.png')});
      await ctx.close();
    }

    // ── (3) open=match_analysis&a=<可發起> → 不點任何東西，工作區出現且 A 已選 ──
    for (const [tag, a, want] of [['initiable A', A_OK, A_OK], ['A not initiable', A_MINE, A_FIRST]]) {
      const ctx = await browser.newContext({viewport: {width: 1440, height: 1000}});
      await offline(ctx);
      const page = await ctx.newPage();
      let clicks = 0;
      await page.exposeFunction('__evaClick', () => { clicks++; });
      await page.addInitScript(() => document.addEventListener('click', e => { if (e.isTrusted) window.__evaClick(); }, true));
      await page.goto(`${base}/sso/handoff?token=${fakeToken('zh-TW')}&open=match_analysis&a=${a}`);
      try {
        await page.waitForFunction(() => {
          const ws = document.getElementById('tangle-ws');
          return ws && !ws.classList.contains('hide');
        }, null, {timeout: 30000});
        let sel = null;
        for (let i = 0; i < 100; i++) {
          const f = matchFrame(page);
          sel = f && await f.evaluate(() => {
            const s = document.querySelector('[data-match-a]');
            return s ? {value: s.value, options: [...s.options].map(o => o.value).filter(Boolean)} : null;
          }).catch(() => null);
          if (sel && sel.options.length) break;
          await page.waitForTimeout(150);
        }
        await page.screenshot({path: path.join(tmp, `open-${tag.replace(/ /g, '_')}.png`)});
        if (!sel) fail(`(3) ${tag}: match panel A select never appeared`);
        else if (clicks) fail(`(3) ${tag}: ${clicks} clicks happened`);
        else if (sel.value !== want) fail(`(3) ${tag}: A=${JSON.stringify(sel.value)} want ${JSON.stringify(want)} (options ${sel.options})`);
        else ok(`(3) ${tag}: workspace opened with no click, A=${JSON.stringify(sel.value)} (options ${sel.options.join(',')})`);
      } catch (e) {
        await page.screenshot({path: path.join(tmp, `open-${tag.replace(/ /g, '_')}-fail.png`)});
        fail(`(3) ${tag}: workspace did not open by itself: ${e.message}`);
      }

      if (tag === 'initiable A') {
        // 同一 cookie 重整：open 只生效一次
        await page.goto(base);
        await waitWelcome(page);
        await page.waitForTimeout(2500);
        if (await wsOpen(page)) fail('(3) reload re-opened the workspace (open must be one-shot)');
        else ok('(3) reload with the same cookie does not auto-open again');
      }
      await ctx.close();
    }
  } catch (e) {
    fail(e.stack || e.message);
  } finally {
    await browser.close();
    srv.kill('SIGTERM');
  }
  if (fails) { console.log(srvLog.slice(-3000)); console.log(`FAILED ${fails} (artifacts: ${tmp})`); process.exit(1); }
  console.log('PASS');
  process.exit(0);
})();
