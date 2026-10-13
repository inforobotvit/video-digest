// Fit check and render for architecture-{light,dark}.html, run by architecture-gen.py.
// Every <text data-box="x,y,w,h,pad"> must lie inside its box inset by pad (12 px for real boxes); every text
// must lie inside the 1280x720 canvas. Any violation: the list is printed, the exit code is 1 and no PNG is written.
// Playwright comes from frontend/node_modules (createRequire), the browser is the same headless Chromium.
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.resolve(here, '../../frontend/package.json'));
const { chromium } = require('@playwright/test');

const browser = await chromium.launch();
let failed = false;
for (const theme of ['light', 'dark']) {
  const ctx = await browser.newContext({ viewport: { width: 1344, height: 800 }, deviceScaleFactor: 3 });
  const page = await ctx.newPage();
  await page.goto(`file://${path.join(here, `architecture-${theme}.html`)}`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(800);
  const problems = await page.evaluate(() => {
    const out = [];
    const r1 = (v) => Math.round(v * 10) / 10;
    for (const t of document.querySelectorAll('svg text')) {
      const b = t.getBBox();
      const label = (t.textContent || '').trim().slice(0, 40);
      if (b.x < 0 || b.y < 0 || b.x + b.width > 1280 || b.y + b.height > 720)
        out.push(`${label}: outside the canvas (${r1(b.x)},${r1(b.y)} ${r1(b.width)}x${r1(b.height)})`);
      const box = t.getAttribute('data-box');
      if (!box) continue;
      const [x, y, w, h, pad] = box.split(',').map(Number);
      const inner = { x: x + pad, y: y + pad, right: x + w - pad, bottom: y + h - pad };
      const over = [];
      if (b.x < inner.x) over.push(`left by ${r1(inner.x - b.x)}`);
      if (b.x + b.width > inner.right) over.push(`right by ${r1(b.x + b.width - inner.right)}`);
      if (b.y < inner.y) over.push(`top by ${r1(inner.y - b.y)}`);
      if (b.y + b.height > inner.bottom) over.push(`bottom by ${r1(b.y + b.height - inner.bottom)}`);
      if (over.length) out.push(`${label}: ${over.join(', ')} (text ${r1(b.width)}x${r1(b.height)}, box ${w}x${h} pad ${pad})`);
    }
    return out;
  });
  if (problems.length) {
    failed = true;
    console.log(`${theme}: ${problems.length} violation(s)`);
    for (const p of problems) console.log('  - ' + p);
  } else {
    await page.locator('svg').screenshot({ path: path.join(here, `architecture-${theme}.png`) });
    console.log(`${theme}: fit check green, PNG written (3840x2160)`);
  }
  await ctx.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
