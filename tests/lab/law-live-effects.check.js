// Finished real result must reuse the accepted galaxy drawing (not the bare progress view):
// glow on hit satellites, evidence dots + moving light flow, gap fog with 缺：…, walking into a satellite shows
// clause debris; clicking a finished satellite asks Eva (domain event) instead of doing nothing.
// Data: tests/lab/law-live-result.json = handler.domain_view() of a real judge run (大庄, 2026-11-19).
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') { res.setHeader('content-type','text/html');
    return res.end('<!doctype html><body><div id="root"></div><script src="/public/tangle-lab-overlay.js"></script></body>'); }
  try { const file = path.join(root, url.pathname);
    res.setHeader('content-type', file.endsWith('.js') ? 'text/javascript' : 'text/html');
    res.end(await fs.readFile(file)); } catch { res.statusCode = 404; res.end(); }
});
(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const law = JSON.parse(await fs.readFile(path.join(__dirname, 'law-live-result.json'), 'utf8'));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}});
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(() => { window.events = []; window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); }); });
    const push = (snap, update=true) => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail:{name:'tangle_workspace', args}})), {mode:'law', lawTask:snap, update});
    const project = {uuid:'48060125', name:'雲林縣二崙鄉大庄社區農村再生計畫'};
    const progress = Object.entries(law).filter(([,v]) => v.total).map(([d,v]) => ({domain:d,total:v.total,hit:v.hit,elapsed:30}));
    await push({task_id:'t1', status:'done', projects:[project], project, progress, result:{summary:'完成', law}, error:null}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.getByText('法規檢核完成').waitFor();
    const galaxy = panel.frameLocator('iframe[title="本次法規檢核星系"]');
    await galaxy.locator('[data-kv-key="農村再生"]').waitFor();
    await page.waitForTimeout(2500);   // entrance finishes
    const g = galaxy.locator('#svg');
    const count = sel => g.locator(sel).count();
    assert.equal(await galaxy.locator('[data-kv-key]').count(), 10, 'all 10 covered domains are satellites');
    assert.equal(await galaxy.locator('[data-kv-state="hit"]').count(), 5);
    assert.equal(await galaxy.locator('[data-kv-state="gap"]').count(), 2);
    assert.equal(await galaxy.locator('[data-kv-state="na"]').count(), 3);
    assert.ok(await count('circle[fill="url(#kv-glow)"]') >= 5, 'glow on hit satellites');
    assert.ok(await count('circle[fill="url(#kv-fog)"]') >= 2, 'fog on gap satellites');
    assert.ok(await count('circle[fill="#b6bfcb"]') >= 10, 'evidence dots around the planet');
    assert.match(await galaxy.locator('[data-kv-key="開發審議"]').textContent(), /缺：/);
    const flow = () => galaxy.locator('body').evaluate(() => typeof PT !== 'undefined' ? PT.map(q => q.u) : []);
    const u0 = await flow(); await page.waitForTimeout(800); const u1 = await flow();
    assert.ok(u0.length > 0 && u0.some((u,i) => u1[i] !== u), 'light flow particles move');
    // walk into a hit satellite: clause debris appears, and Eva is asked about that domain
    await galaxy.locator('[data-kv-key="農村再生"]').press('Enter');
    await galaxy.locator('[data-focus="農村再生"]').waitFor();
    await page.waitForTimeout(1500);
    assert.ok(await count('[data-clause]') >= 5, 'clause debris around the focused satellite');
    await page.waitForFunction(() => events.some(e => e.action === 'domain'));
    assert.deepEqual(await page.evaluate(() => events.find(e => e.action === 'domain')), {kind:'law_task', action:'domain', task_id:'t1', domain:'農村再生'});
    assert.deepEqual(errors, []);
    console.log('PASS live law effects reuse the accepted drawing');
  } finally { await browser.close(); server.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
