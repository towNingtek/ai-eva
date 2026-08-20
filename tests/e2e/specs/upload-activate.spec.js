// #112 KPI「檢核時可引用已上傳法規資料」——上傳的法規要真的能被檢核引用。
//
// 這條是完整鏈路：上傳（pending，不影響判定）→ 管理者啟用（就地建索引）
// → 執行檢核 → 報告的逐條判定總表引用到它。
const { test, expect } = require('@playwright/test');
const path = require('node:path');
const { loginViaSSO, runCommand, openTool, waitForText } = require('./helpers');

/** 取畫面上**最後一次**出現的數字：啟用後面板會重新渲染一次，
 *  舊面板還留在對話裡，抓第一筆會讀到啟用前的舊值。 */
function lastNumber(text, pattern) {
  const all = [...text.matchAll(pattern)];
  expect(all.length, `畫面上找不到 ${pattern}`).toBeGreaterThan(0);
  return Number(all[all.length - 1][1]);
}

// 語料庫沒收的一部法規（用 Drive 語料裡的檔案當上傳來源，內容是真的法規全文）
const UPLOAD_PDF = path.join(__dirname, '..', '..', '..',
  'app', 'regulations', 'corpus', 'raw', '農村再生條例施行細則.pdf');
const UPLOAD_NAME = '農村再生條例施行細則';

test.describe('#112 上傳 → 啟用 → 被檢核引用', () => {
  test('啟用後才進判定分母，且檢核報告引用得到', async ({ page }) => {
    await loginViaSSO(page);

    // 1. 上傳 → 待審核
    await page.locator('#upload-button-input').setInputFiles(UPLOAD_PDF);
    await expect(page.getByText(`${UPLOAD_NAME}.pdf`).first()).toBeVisible({ timeout: 60_000 });
    await runCommand(page, '法規知識庫', '上傳法規');
    // 等「這一部」出現在待審核清單裡 —— 只等「待審核」字樣的話，
    // 上一輪測試留下的 pending 就會讓斷言誤判成功，然後卡在按一顆不存在的按鈕上
    await waitForText(page, `啟用 ${UPLOAD_NAME}`.slice(0, 12), 120_000);
    await expect(
      page.getByRole('button', { name: new RegExp(`啟用 ${UPLOAD_NAME}`) }).first(),
      '待審核清單裡沒有這次上傳的法規',
    ).toBeVisible({ timeout: 60_000 });

    const afterUpload = await page.evaluate(() => document.body.innerText);
    const activeBefore = lastNumber(afterUpload, /(\d+)\s*部生效/g);
    expect(afterUpload).toContain('按「啟用」才會納入檢核');

    // 2. 按啟用 → 就地建索引（抽條文與管制條目）
    await page.getByRole('button', { name: new RegExp(`啟用 ${UPLOAD_NAME}`) }).first().click();
    await waitForText(page, '已啟用並建立索引', 5 * 60 * 1000);

    const afterActivate = await page.evaluate(() => document.body.innerText);
    expect(afterActivate).toMatch(/\*{0,2}\d+\*{0,2}\s*條文\s*→\s*\*{0,2}\d+\*{0,2}\s*條管制條目/);
    // 生效部數要 +1（治理閘門：啟用前後的差別要看得出來）
    const activeAfter = lastNumber(afterActivate, /(\d+)\s*部生效/g);
    expect(activeAfter, '啟用後生效部數沒有增加').toBe(activeBefore + 1);

    // 3. 跑檢核 → 報告要引用得到這部法規
    await openTool(page, '法規檢核');
    await waitForText(page, '份你可管理的計畫書', 120_000);
    await page.locator('#chat-input').fill('晴耕');
    await page.locator('#chat-submit').click();
    await waitForText(page, '檢核完成', 5 * 60 * 1000);

    const link = page.getByRole('link', { name: /法規檢核報告_.*\.md/ }).first();
    await expect(link).toBeVisible({ timeout: 60_000 });
    const res = await page.request.get(await link.getAttribute('href'));
    expect(res.status()).toBe(200);
    const md = await res.text();
    expect(md, `報告沒有引用到上傳並啟用的「${UPLOAD_NAME}」`).toContain(UPLOAD_NAME);
  });
});
