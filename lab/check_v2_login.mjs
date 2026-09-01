import { chromium } from 'playwright-core';
import fs from 'node:fs';
import crypto from 'node:crypto';

const profile = process.argv[2];
const executable = process.argv[3] || 'E:\\WB\\tools\\bsk-file-bridge\\cft\\chrome-win64\\chrome.exe';
const ctx = await chromium.launchPersistentContext(profile, {
  headless: false,
  executablePath: executable,
  args: ['--disable-blink-features=AutomationControlled'],
});
try {
  const page = ctx.pages()[0] || await ctx.newPage();
  page.setDefaultTimeout(30000);
  await page.goto('https://chatgpt.com/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(4000);
  const selectors = ['#prompt-textarea', 'div.ProseMirror[contenteditable="true"]', '[contenteditable="true"][data-virtualkeyboard="true"]', 'textarea[placeholder*="Message"]'];
  const counts = {};
  let composer = 0;
  for (const s of selectors) {
    const n = await page.locator(s).count();
    counts[s] = n;
    composer += n;
  }
  const bodyText = await page.locator('body').innerText().catch(() => '');
  const signals = {
    login_visible: /log in|sign in|登录/i.test(bodyText),
    signup_visible: /sign up|注册/i.test(bodyText),
    human_verification: /verify you are human|checking your browser|challenge/i.test(bodyText),
  };
  const shot = 'E:\\WB\\outputs\\ai-production-control\\v2-login-check.png';
  await page.screenshot({ path: shot });
  console.log(JSON.stringify({
    url: page.url(),
    title: await page.title(),
    composer_total: composer,
    counts,
    signals,
    screenshot_sha256: crypto.createHash('sha256').update(fs.readFileSync(shot)).digest('hex'),
    verdict: composer > 0 ? 'LOGGED_IN' : (signals.login_visible || signals.signup_visible ? 'AUTH_EXPIRED' : 'UI_CHANGED'),
  }, null, 1));
} finally {
  await ctx.close();
}
