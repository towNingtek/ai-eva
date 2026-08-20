// 從輸入框旁的「...」工具選單挑 app，也要真的跑起來。
//
// Chainlit 的 command 選了只是掛到輸入框上、不會送出；repo 早期在 public/custom.js
// 補了一段自動送出的 shim，但寫死只認「圖表分析 / 社群貼文」，其他 app 從選單點
// 完全沒反應（使用者實際回報）。這支測試守住「每個選單項目都送得出去」。
const { test, expect } = require('@playwright/test');
const { loginViaSSO, runCommandViaMenu, waitForText } = require('./helpers');

test.describe('工具選單（Chainlit command）', () => {
  test('從選單點「法規知識庫」會自動送出並出面板', async ({ page }) => {
    await loginViaSSO(page);
    await runCommandViaMenu(page, '法規知識庫');
    await waitForText(page, '部生效', 90_000);
  });

  test('從選單點「法規檢核」會自動送出並出引導詞', async ({ page }) => {
    await loginViaSSO(page);
    await runCommandViaMenu(page, '法規檢核');
    await waitForText(page, '正在讀取你可管理的計畫書', 60_000);
  });
});
