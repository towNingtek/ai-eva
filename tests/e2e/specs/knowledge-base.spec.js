// #112 知識庫管理（法規資料）—— KPI：可上傳 PDF、可重複使用既有索引、檢核時可引用
const { test, expect } = require('@playwright/test');
const path = require('node:path');
const { loginViaSSO, runCommand, openTool, waitForText } = require('./helpers');

test.describe('#112 知識庫管理', () => {
  test('KPI: 可重複使用已建立之法規索引（開機直接就緒，不必重跑 ingest）', async ({ page }) => {
    await loginViaSSO(page);
    await openTool(page, '法規知識庫');
    await waitForText(page, '部生效', 60_000);

    const body = await page.evaluate(() => document.body.innerText);
    // 語料庫是 repo 帶進來、開機 seed 的：一進來就有生效法規與管制條目
    expect(body).toMatch(/(\d+)\s*部生效/);
    expect(body).toMatch(/條文/);
    expect(body).toMatch(/條管制/);
    expect(body).toMatch(/個法領域/);

    const active = Number(body.match(/(\d+)\s*部生效/)[1]);
    expect(active).toBeGreaterThanOrEqual(20);   // 語料 31 檔，扣掉草案與無全文者

    // 清單看得到法規逐部列出（含條文數／管制數），代表索引可重複引用
    await expect(page.getByText('水土保持法').first()).toBeVisible();
    await expect(page.getByText('農業發展條例').first()).toBeVisible();
  });

  test('KPI: 法規 PDF 可上傳，且上傳後為待審核、不影響判定', async ({ page }) => {
    await loginViaSSO(page);

    // 先掛附件再叫 app：先開面板的話 #upload-button-input 會被重繪，setInputFiles 會打到舊節點
    const pdf = path.join(__dirname, '..', '..', '..',
      'app', 'regulations', 'corpus', 'raw', '水土保持法.pdf');
    await page.locator('#upload-button-input').setInputFiles(pdf);
    await expect(page.getByText('水土保持法.pdf').first()).toBeVisible({ timeout: 60_000 });

    await runCommand(page, '法規知識庫');
    await waitForText(page, '待審核', 120_000);

    const body = await page.evaluate(() => document.body.innerText);
    // KPI：PDF 上傳成功，且明確標示為待審核
    expect(body).toMatch(/已收到\s*\**\d+\**\s*份上傳的法規/);
    expect(body).toContain('待審核');

    // 治理閘門：待審核不進判定分母 —— 生效部數不因上傳而增加
    expect(body).toContain('未經啟用前不會影響檢核結果');
    const active = Number(body.match(/(\d+)\s*部生效/)[1]);
    expect(active).toBe(28);
  });
});
