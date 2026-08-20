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
 * Chainlit 把 commands 收在輸入框旁的「...」展開鈕後面（不是常駐 chip），
 * 所以要先展開再點。 */
async function runCommand(page, label, text = '') {
  await page.getByRole('button', { name: '...' }).first().click();
  // 一定要限定在展開的選單裡（role=option）：歡迎訊息也有同名的工具按鈕，
  // 不限定會誤點到它、而且它被選單遮住 → 整個卡死
  await page.getByRole('option', { name: label }).first().click();
  // 選 command 只是把它掛到輸入框上，還要送出才會派工（main.py on_message 靠 msg.command 分派）。
  // 用送出鈕而不是 Enter：帶附件時 Enter 不一定會觸發送出。
  const input = page.locator('#chat-input');
  await input.click();
  if (text) await input.fill(text);
  const submit = page.locator('#chat-submit');
  await submit.waitFor({ state: 'visible', timeout: 10_000 });
  await submit.click();
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

module.exports = { token, loginViaSSO, runCommand, openTool, waitForText };
