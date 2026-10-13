import { MOCK } from '@/api/client';

/**
 * Cloudflare Turnstile on the run form (step E3, 2026-09-29): explicit render, one widget, action create_job,
 * reset after every submit attempt (a token is single-use and lives 5 minutes). The site key comes from
 * VITE_TURNSTILE_SITE_KEY at build time; the mock and e2e use Cloudflare's test key that always passes. No key –
 * no widget, no token: the server decides what a missing token means (monitor or enforce).
 */
export const TEST_SITE_KEY_PASS = '1x00000000000000000000AA';
const SCRIPT = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';

interface TurnstileApi {
  render(el: HTMLElement, opts: Record<string, unknown>): string;
  reset(id: string): void;
  remove(id: string): void;
}
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}

export function siteKey(): string | null {
  const k = (import.meta.env.VITE_TURNSTILE_SITE_KEY as string | undefined)?.trim();
  if (k) return k;
  return MOCK ? TEST_SITE_KEY_PASS : null;
}

// One widget per container: React's StrictMode runs an effect twice, and two renders into the same element race
// (the removal of the first cleared the second). A new render into an element first removes the widget it holds.
const held = new WeakMap<HTMLElement, Widget>();
let loading: Promise<TurnstileApi | null> | null = null;
/** Loads api.js once; resolves null when the script cannot load (blocked, offline) – the form then runs without a token. */
export function loadTurnstile(): Promise<TurnstileApi | null> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (loading) return loading;
  loading = new Promise((resolve) => {
    const s = document.createElement('script');
    s.src = SCRIPT;
    s.async = true;
    s.onload = () => resolve(window.turnstile ?? null);
    s.onerror = () => resolve(null);
    document.head.appendChild(s);
  });
  return loading;
}

export interface Widget {
  id: string;
  reset: () => void;
  remove: () => void;
}

/** Renders the widget into `el`; `onToken` gets the token, and null when it expires or the challenge errors. */
export async function renderTurnstile(
  el: HTMLElement,
  onToken: (token: string | null) => void,
): Promise<Widget | null> {
  const key = siteKey();
  if (!key) return null;
  const api = await loadTurnstile();
  if (!api || !el.isConnected) return null;
  held.get(el)?.remove();
  const id = api.render(el, {
    sitekey: key,
    action: 'create_job',
    callback: (token: string) => onToken(token),
    'expired-callback': () => onToken(null),
    'error-callback': () => onToken(null),
    'timeout-callback': () => onToken(null),
  });
  let removed = false;
  const widget: Widget = {
    id,
    reset: () => {
      onToken(null);
      try {
        api.reset(id);
      } catch {
        /* widget already gone */
      }
    },
    remove: () => {
      if (removed) return;
      removed = true;
      if (held.get(el) === widget) held.delete(el);
      try {
        api.remove(id);
      } catch {
        /* widget already gone */
      }
    },
  };
  held.set(el, widget);
  return widget;
}
