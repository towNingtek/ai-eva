const { defineConfig } = require('@playwright/test');

// 法規檢核是 PUSH 流程（整份計畫逐條比對，實測 45~120 秒），
// 預設 30 秒 timeout 一定不夠 —— 這裡放寬到 6 分鐘。
module.exports = defineConfig({
  testDir: './specs',
  timeout: 6 * 60 * 1000,
  expect: { timeout: 30 * 1000 },
  fullyParallel: false,      // 同一個 chainlit session，不並行
  workers: 1,
  retries: 0,
  globalSetup: require.resolve('./global-setup.js'),
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.EVA_BASE_URL || 'http://localhost:7871',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    acceptDownloads: true,
  },
});
