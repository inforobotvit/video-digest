#!/usr/bin/env node
/**
 * Real playback check for the result-page player: drives headless Google Chrome (no extensions)
 * over CDP, opens a job page on the dev server, clicks a timecode with a real mouse event (which
 * gives user activation, element.click() does not) and reports the player state plus the
 * postMessage traffic from the platform frame. Needed because the automation tab used for
 * screenshots never loads media and blocks Rutube.
 *
 *   node scripts/player-check.mjs [url] [origin-substring] [--expand]
 *
 *   url               page to test, default http://localhost:5173/jobs/rutube (dev server with VITE_MOCK=1)
 *   origin-substring  which postMessage origins to log, default "rutube" (use "youtube" for YouTube jobs)
 *   --expand          press «Картинка» before clicking, to compare the collapsed and expanded bar
 *
 * Expected on success: `playing: "Пауза"`, the time a few seconds past the clicked timecode and
 * `n` well above zero. Zero messages means the platform player never initialised (for Rutube that
 * happens when its iframe is clipped or outside the viewport).
 */
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const url = args[0] ?? 'http://localhost:5173/jobs/rutube';
const originPattern = args[1] ?? 'rutube';
const expandFirst = process.argv.includes('--expand');
// --early: click before the player is ready, the way an impatient reader does.
const early = process.argv.includes('--early');
const chromePath =
  process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const port = 9333;
const profile = mkdtempSync(join(tmpdir(), 'player-check-'));

const chrome = spawn(chromePath, [
  '--headless=new',
  `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`,
  '--no-first-run',
  '--window-size=1400,900',
  '--mute-audio',
  'about:blank',
]);
chrome.on('error', (e) => {
  console.error(`cannot start Chrome at ${chromePath}: ${e.message} (set CHROME_PATH)`);
  process.exit(1);
});
chrome.stderr.on('data', () => {});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let targets = [];
for (let i = 0; i < 40 && targets.length === 0; i++) {
  await sleep(250);
  try {
    const list = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    targets = list.filter((t) => t.type === 'page');
  } catch {
    /* not up yet */
  }
}
if (targets.length === 0) {
  console.error('Chrome did not expose a page target');
  chrome.kill();
  process.exit(1);
}

const ws = new WebSocket(targets[0].webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0;
const pending = new Map();
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.id && pending.has(m.id)) {
    pending.get(m.id)(m.result ?? m.error);
    pending.delete(m.id);
  }
};
const send = (method, params = {}) =>
  new Promise((r) => {
    const n = ++id;
    pending.set(n, r);
    ws.send(JSON.stringify({ id: n, method, params }));
  });
const evaluate = async (expression) => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  return r.result && 'value' in r.result ? r.result.value : r;
};

await send('Page.enable');
// Log the platform frame's messages from the first one, and note when the player said ready.
await send('Page.addScriptToEvaluateOnNewDocument', {
  source: `window.__msgs = []; window.__t0 = Date.now(); window.__ready = null;
    window.addEventListener('message', e => {
      if (!String(e.origin).includes(${JSON.stringify(originPattern)})) return;
      const s = String(e.data);
      if (window.__ready === null && /player:ready|onReady|initialDelivery|"inited"/.test(s)) window.__ready = Date.now() - window.__t0;
      window.__msgs.push(s.slice(0, 90));
    });`,
});
await send('Page.navigate', { url });
// Wait for the player to report ready, up to 25 s (Rutube's CDN can be slow).
let readyAfter = null;
for (let i = 0; i < 50 && readyAfter === null && !early; i++) {
  await sleep(500);
  readyAfter = await evaluate('window.__ready ?? null');
}
await sleep(1000);
if (expandFirst) {
  await evaluate(
    `[...document.querySelectorAll('button.pbtn')].find(b => b.textContent.trim() === 'Картинка')?.click(); 'ok'`,
  );
  await sleep(2000);
}
const target = await evaluate(
  `(() => { const b = [...document.querySelectorAll('button.tc')][2]; if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, label: b.textContent }; })()`,
);
if (!target) {
  console.error('no timecode button on the page: is the dev server up and the job done?');
  ws.close();
  chrome.kill();
  process.exit(1);
}
for (const type of ['mousePressed', 'mouseReleased'])
  await send('Input.dispatchMouseEvent', {
    type,
    x: target.x,
    y: target.y,
    button: 'left',
    clickCount: 1,
  });
await sleep(8000);
if (early) {
  // Second act of the impatient reader: the play button once the player is up.
  const play = await evaluate(
    `(() => { const b = document.querySelector('.player__play'); if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`,
  );
  if (play)
    for (const type of ['mousePressed', 'mouseReleased'])
      await send('Input.dispatchMouseEvent', {
        type,
        x: play.x,
        y: play.y,
        button: 'left',
        clickCount: 1,
      });
  await sleep(6000);
}

const state = await evaluate(`({
  readyAfterMs: ${JSON.stringify(readyAfter)},
  clicked: ${JSON.stringify(target.label)},
  time: document.querySelector('.player__time')?.textContent,
  playing: document.querySelector('.player__play')?.getAttribute('aria-label') ?? '(expanded)',
  failed: document.querySelector('.strip__failed')?.textContent ?? null,
  frame: document.querySelector('.player__media iframe')?.getBoundingClientRect().toJSON(),
  n: window.__msgs.length,
  types: [...new Set(window.__msgs.map(m => (m.match(/"(?:type|event)":"([^"]+)"/) || [])[1] || m.slice(0, 30)))],
  last: window.__msgs.slice(-3),
})`);
console.log(JSON.stringify(state, null, 2));
ws.close();
chrome.kill();
