const fs = require('node:fs');
const path = require('node:path');

function token() {
  return fs.readFileSync(path.join(__dirname, '..', '.auth', 'token.txt'), 'utf8').trim();
}

/** 走 SSO handoff 進站（等同使用者在 CMS 按「進 AI Eva」），停在已登入的對話頁。 */
async function loginViaSSO(page) {
  await page.goto(`/sso/handoff?token=${token()}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('#chat-input', { timeout: 30_000 });
  // 工具選單是 on_chat_start 非同步註冊的，等它出現再往下走
  await page.waitForFunction(
    () => document.body.innerText.includes('AI 副駕') || document.body.innerText.includes('Eva'),
    null, { timeout: 30_000 });
}

/** 開工具選單並選一個 app。
 *
 * 選完**不要**自己填字或按送出：public/custom.js 有一段自動送出的 shim，
 * 而它只在輸入框是空的時候才動作 —— 先填字反而會把它擋掉，兩邊打架。
 * 這也正是真實使用者的操作：從選單點一下，就這樣。
 */
async function runCommand(page, label) {
  await runCommandViaMenu(page, label);
}

/** 只從「...」選單挑 app，**不自己按送出** —— 驗 custom.js 的自動送出有沒有生效。 */
async function runCommandViaMenu(page, label) {
  await page.getByRole('button', { name: '...' }).first().click();
  await page.getByRole('option', { name: label }).first().click();
}

/** 點歡迎訊息上的工具按鈕（cl.Action）—— 點了直接跑，不必送訊息。 */
async function openTool(page, label) {
  await page.getByRole('button', { name: label }).first().click();
}

/** 等某段文字出現在對話裡（app 的回覆多半是非同步長流程）。 */
async function waitForText(page, text, timeout = 5 * 60 * 1000) {
  await page.waitForFunction(
    (t) => document.body.innerText.includes(t), text, { timeout, polling: 1000 });
}

module.exports = { token, loginViaSSO, runCommand, runCommandViaMenu, openTool, waitForText };
