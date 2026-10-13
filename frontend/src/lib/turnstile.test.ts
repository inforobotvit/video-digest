// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/client', () => ({ MOCK: true }));
const { loadTurnstile, renderTurnstile, siteKey, TEST_SITE_KEY_PASS } = await import('./turnstile');

type Opts = Record<string, unknown> & {
  callback?: (t: string) => void;
  'expired-callback'?: () => void;
};
let rendered: { el: HTMLElement; opts: Opts }[];
const fake = {
  render: vi.fn((el: HTMLElement, opts: Opts) => {
    rendered.push({ el, opts });
    return `w${rendered.length}`;
  }),
  reset: vi.fn(),
  remove: vi.fn(),
};

beforeEach(() => {
  rendered = [];
  fake.render.mockClear();
  fake.reset.mockClear();
  fake.remove.mockClear();
  window.turnstile = fake;
});
afterEach(() => {
  delete window.turnstile;
});

describe('turnstile', () => {
  it('the mock uses the Cloudflare test key that always passes', () => {
    expect(siteKey()).toBe(TEST_SITE_KEY_PASS);
  });

  it('renders once with the create_job action; the token flows out, expiry clears it, reset clears and resets', async () => {
    const el = document.createElement('div');
    document.body.appendChild(el);
    const onToken = vi.fn();
    const w = await renderTurnstile(el, onToken);
    expect(w?.id).toBe('w1');
    expect(fake.render).toHaveBeenCalledTimes(1);
    expect(rendered[0].opts.sitekey).toBe(TEST_SITE_KEY_PASS);
    expect(rendered[0].opts.action).toBe('create_job');
    rendered[0].opts.callback!('tok-1');
    expect(onToken).toHaveBeenLastCalledWith('tok-1');
    rendered[0].opts['expired-callback']!();
    expect(onToken).toHaveBeenLastCalledWith(null);
    w!.reset();
    expect(fake.reset).toHaveBeenCalledWith('w1');
    expect(onToken).toHaveBeenLastCalledWith(null);
    w!.remove();
    expect(fake.remove).toHaveBeenCalledWith('w1');
    el.remove();
  });

  it('a detached container renders nothing', async () => {
    const el = document.createElement('div');
    expect(await renderTurnstile(el, vi.fn())).toBeNull();
    expect(fake.render).not.toHaveBeenCalled();
  });

  it('loadTurnstile resolves the api when the script is already there', async () => {
    expect(await loadTurnstile()).toBe(fake);
  });
});
