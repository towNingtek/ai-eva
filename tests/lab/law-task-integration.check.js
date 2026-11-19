// Start law-task-fixture.py first; pass its loopback URL as argv[2].
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const {chromium} = require('playwright');

(async () => {
  const url = process.argv[2] || 'http://127.0.0.1:8794';
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({acceptDownloads:true, reducedMotion:'reduce'});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const state = async () => (await page.request.get(`${url}/fixture/state`)).json();
    await page.goto(url);
    await page.locator('#open').click();
    const panel = page.frameLocator('#tangle-ws iframe');
    await panel.getByLabel('分析專案').waitFor();
    await panel.getByRole('button',{name:'開始法規檢核'}).click();
    await panel.getByText('各法領域進度').waitFor();
    const running = await state();
    assert.equal(running.judgeCalls, 1);
    assert.equal(running.persisted.status, 'running');
    assert.equal(running.attachmentCount, 0);
    const taskId = running.persisted.task_id;
    // Replay select to prove the real task deduplicates starts, not just the UI.
    await page.evaluate(({taskId, uuid}) => window.postMessage({tangle:{kind:'law_task',action:'select', task_id:taskId,uuid}}, location.origin), {taskId, uuid:running.persisted.project.uuid});
    await page.locator('#tangle-ws-close').click();
    await page.waitForFunction(() => !window.__tangleWS.state.open);
    await page.locator('#open').click();
    await page.waitForFunction(() => window.__tangleWS.state.open);
    await panel.getByText('各法領域進度').waitFor();
    await panel.getByText('正在進行法規檢核…').waitFor();
    assert.equal((await state()).persisted.task_id, taskId);
    await page.request.post(`${url}/fixture/release`);
    await panel.getByRole('button',{name:'回到聊天下載報告'}).click();
    await page.waitForFunction(() => !window.__tangleWS.state.open);
    const link = page.locator('#chat a');
    await link.waitFor();
    const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
    const done = await state();
    assert.equal(done.judgeCalls, 1);
    assert.equal(done.attachmentCount, 1);
    assert.equal(done.persisted.task_id, taskId);
    assert.equal(done.persisted.status, 'done');
    assert.equal(download.suggestedFilename(), done.persisted.result.attachment.name);
    assert.equal(await link.getAttribute('id'), done.persisted.result.attachment.message_id);
    const actualMd = await fs.readFile(await download.path());
    assert.deepEqual(actualMd, Buffer.from(done.expectedMd, 'base64'));
    assert.match(actualMd.toString('utf8'), /原始報告測試證據/);
    await page.locator('#open').click();
    await page.waitForFunction(() => window.__tangleWS.state.open);
    await panel.getByRole('button',{name:'回到聊天下載報告'}).waitFor();
    assert.equal((await state()).persisted.task_id, taskId);
    await panel.getByRole('button',{name:'開始新的法規檢核'}).click();
    await panel.getByLabel('分析專案').waitFor();
    const fresh = await state();
    assert.notEqual(fresh.persisted.task_id, taskId);
    assert.equal(fresh.persisted.status, 'select');
    assert.equal(fresh.judgeCalls, 1);
    assert.equal(fresh.attachmentCount, 1);
    assert.deepEqual(errors, []);
    console.log('PASS Playwright + actual regulation task persistence/report bytes (loopback transport fixture)');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
