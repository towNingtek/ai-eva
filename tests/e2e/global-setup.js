// 每次跑測試前簽一張新的 handoff token（TTL 只有 10 分鐘，不能寫死在檔案裡）。
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async () => {
  const dir = path.join(__dirname, '.auth');
  fs.mkdirSync(dir, { recursive: true });
  const token = execFileSync(path.join(__dirname, 'mint-token.sh'), { encoding: 'utf8' }).trim();
  if (!token.startsWith('ey')) throw new Error(`mint-token.sh 沒有回傳 JWT：${token.slice(0, 120)}`);
  fs.writeFileSync(path.join(dir, 'token.txt'), token);
  process.env.EVA_SSO_TOKEN = token;
};
