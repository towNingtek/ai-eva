// 工具按鈕：選單裡的 command 選了還要按送出才會跑，第一次用的人會以為壞掉。
// 歡迎訊息掛的 Action 按鈕點下去要直接動起來。
const { test, expect } = require('@playwright/test');
const { loginViaSSO, waitForText } = require('./helpers');

test.describe('工具按鈕（cl.Action）', () => {
  test('歡迎訊息列出工具，點一下就跑起來（不必再送訊息）', async ({ page }) => {
    await loginViaSSO(page);

    // 按鈕要在歡迎訊息就看得到
    const btn = page.getByRole('button', { name: /法規檢核/ }).first();
    await expect(btn, '歡迎訊息沒有列出「法規檢核」按鈕').toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole('button', { name: /法規知識庫/ }).first()).toBeVisible();

    // 點下去就該動，不需要再按送出
    await btn.click();
    await waitForText(page, '正在讀取你可管理的計畫書', 30_000);
    await waitForText(page, '份你可管理的計畫書', 120_000);
  });

  test('知識庫按鈕點一下直接出面板', async ({ page }) => {
    await loginViaSSO(page);
    await page.getByRole('button', { name: /法規知識庫/ }).first().click();
    await waitForText(page, '部生效', 60_000);
    const body = await page.evaluate(() => document.body.innerText);
    expect(body).toMatch(/(\d+)\s*部生效/);
    expect(body).toContain('條管制');
  });
});
