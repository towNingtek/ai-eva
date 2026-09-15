// #111 法規檢核 —— KPI：完整流程產出 5 區塊 .md、涵蓋 10 法領域（範圍外標未評估）、可下載
const { test, expect } = require('@playwright/test');
const { loginViaSSO, runCommand, waitForText } = require('./helpers');

const PLAN = '晴耕社區';   // R0 盲生的測試計畫書（uuid 90948229）

test.describe('#111 法規檢核', () => {
  test('端到端：接收計畫書 → 檢核 → 5 區塊 .md 報告可下載', async ({ page }) => {
    await loginViaSSO(page);
    await runCommand(page, '法規檢核');

    // 點下工具要立刻有回應（不能靜默）——使用者最容易在這裡以為點壞了
    await waitForText(page, '法規檢核', 20_000);
    await waitForText(page, '正在讀取你可管理的計畫書', 20_000);

    // 專案選單（CMS list_my_projects → get_project_info 並行拉回）
    // 首次抓清單要對 CMS 打 1+N 次（走 tunnel 會更慢），給寬一點
    await waitForText(page, '份你可管理的計畫書', 240_000);
    const listing = await page.evaluate(() => document.body.innerText);
    expect(listing).toContain(PLAN);
    // 關鍵字就該選得到，不必打完整名稱
    await page.locator('#chat-input').fill(PLAN);
    await page.locator('#chat-submit').click();

    // 判定是 PUSH 非即時流程，實測 45~120 秒
    await waitForText(page, '開始檢核', 60_000);
    await waitForText(page, '檢核完成', 5 * 60 * 1000);

    const body = await page.evaluate(() => document.body.innerText);

    // KPI 1：流程走完並產出摘要
    expect(body).toMatch(/違規風險\s*\**\d+/);
    expect(body).toMatch(/合規提醒\s*\**\d+/);
    expect(body).toMatch(/逐條評估\s*\d+\s*條管制條目/);

    // 判定真的有跑（不是每批都失敗）——judge 對失敗批次會回「判定失敗」佔位，
    // 報告照樣有 5 區塊，只驗結構會拿到假綠燈（實測踩過：模型別名錯，400 全滅仍「通過」）
    const violations = Number(body.match(/違規風險\s*\**(\d+)/)[1]);
    const reminders = Number(body.match(/合規提醒\s*\**(\d+)/)[1]);
    expect(violations + reminders,
      '判定結果全空 —— 檢查 judge 模型別名與 LiteLLM 連線').toBeGreaterThan(0);

    // 進度列：每個法領域跑完都要留下痕跡（覆蓋率看得見）
    for (const domain of ['水土保持', '農業發展', '區域計畫', '環境影響評估']) {
      expect(body, `進度列少了法領域：${domain}`).toContain(domain);
    }

    // KPI 3：報告可下載
    // Chainlit 的檔案元素是一條 /project/file/<id> 連結（不是 <a download>），
    // 點下去是導頁不會觸發 download 事件 —— 直接抓 href 取檔才是真的驗「拿得到檔案」。
    const link = page.getByRole('link', { name: /法規檢核報告_.*\.md/ }).first();
    await expect(link).toBeVisible({ timeout: 60_000 });
    const href = await link.getAttribute('href');
    expect(href, '報告連結沒有 href').toBeTruthy();
    expect(await link.innerText()).toMatch(/\.md$/);

    const res = await page.request.get(href);
    expect(res.status(), `下載報告失敗：${href}`).toBe(200);
    const md = await res.text();
    expect(md.length, '下載到的報告是空的').toBeGreaterThan(1000);

    // KPI 1：5 區塊齊全
    for (const section of ['一、摘要', '二、違規風險', '三、合規提醒',
                           '四、需補語料', '五、免責聲明']) {
      expect(md, `報告缺少區塊：${section}`).toContain(section);
    }

    // KPI 2：宣告涵蓋 10 個法領域，範圍外標「未評估」且不代表合規
    expect(md).toMatch(/宣告涵蓋\s*\**10\s*個法領域/);
    expect(md).toContain('未評估不代表合規');
    expect(md).toContain('未涵蓋領域');

    // 逐條判定總表 = 覆蓋率的稽核依據（甲方要查得到某一條有沒有被檢核）
    expect(md).toContain('逐條判定總表');
    expect(md).toContain('水土保持法');

    // 同上，報告內文也不該出現判定失敗
    expect(md, '報告出現「判定失敗」，代表有批次沒跑成功').not.toContain('判定失敗');

    // 免責：不構成行政處分依據
    expect(md).toContain('不構成行政處分依據');

    // 可追溯：標準版本 / 判定引擎 / 語料版本都要在報告裡
    expect(md).toContain('標準版本');
    expect(md).toContain('判定引擎');
    expect(md).toContain('語料版本');
  });
});
