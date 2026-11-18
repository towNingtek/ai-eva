// Isolated static browser contract check; needs Playwright (can be provided via NODE_PATH).
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require('playwright');
const root = path.resolve(__dirname, '../..');
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') {
    res.setHeader('Content-Type', 'text/html');
    return res.end('<!doctype html><body><div id="root"></div><script src="/public/tangle-lab-overlay.js"></script></body>');
  }
  try {
    const file = path.join(root, url.pathname);
    const bytes = await fs.readFile(file);
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream');
    res.end(bytes);
  } catch { res.writeHead(404); res.end(); }
});
(async () => {
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({viewport:{width:1280,height:900}, reducedMotion:'reduce'});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}`);
    await page.evaluate(() => {
      window.events = [];
      window.addEventListener('message', e => { if (e.data?.tangle) events.push(e.data.tangle); });
    });
    const call = (args) => page.evaluate(args => window.dispatchEvent(new CustomEvent('chainlit-call-fn', {detail:{name:'tangle_workspace', args}})), args);
    const push = (snapshot, update=true) => call({mode:'law', lawTask:snapshot, update});
    const projects = [{uuid:'one',name:'第一案'},{uuid:'two',name:'<b>真實案</b>'}];
    const s = {task_id:'task-1',projects,project:null,progress:[]};
    const waitAction = action => page.waitForFunction(action => events.some(e => e.action === action), action);
    await push({...s,status:'loading'}, false);
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.getByText('載入專案清單中…').waitFor();
    await waitAction('get');
    await push({...s,status:'select'});
    await panel.getByLabel('分析專案').selectOption('two');
    await panel.getByRole('button',{name:'開始法規檢核'}).click();
    await waitAction('select');
    assert.deepEqual(await page.evaluate(() => events.find(e=>e.action==='select')), {kind:'law_task',action:'select',task_id:'task-1',uuid:'two'});
    const r = {...s,status:'running',project:projects[1],progress:[{domain:'測試法領域',total:8,hit:1,elapsed:1.25}]};
    await push(r);
    await panel.getByText('各法領域進度').waitFor();
    const galaxy = panel.frameLocator('iframe[title="本次法規檢核星系"]');
    const domain = galaxy.locator('[data-kv-key="測試法領域"]');
    await domain.waitFor();
    assert.equal(await galaxy.locator('[data-kv-key]').count(),1);
    await domain.press('Enter');
    await galaxy.locator('[data-focus="測試法領域"]').waitFor();
    await push({...r,status:'done',result:{summary:'檢核摘要',attachment:{message_id:'m',name:'正式報告.md'}}});
    await panel.getByText('檢核摘要').waitFor();
    await galaxy.locator('[data-focus="測試法領域"]').waitFor();
    await panel.getByRole('button',{name:'開始新的法規檢核'}).click();
    await waitAction('new');
    assert.deepEqual(await page.evaluate(() => events.find(e=>e.action==='new')), {kind:'law_task',action:'new',task_id:'task-1'});
    await push({...r,task_id:'task-2',status:'error',error:'失敗訊息'});
    await panel.getByText('失敗訊息').waitFor();
    await push({...r,task_id:'task-2',status:'done'});
    await panel.getByRole('button',{name:'回到聊天下載報告'}).click();
    await page.waitForFunction(() => !window.__tangleWS.state.open);
    await push(r);
    assert.equal(await page.evaluate(() => window.__tangleWS.state.open),false);
    await call({mode:'match'});
    await panel.locator('#deskTitle').getByText(/媒合分析/).waitFor();
    await push(r);
    assert.match(await page.locator('#tangle-ws iframe').getAttribute('src'), /mode=match/);
    assert.deepEqual(errors, []);
    console.log('PASS law task browser contract');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => server.close());
