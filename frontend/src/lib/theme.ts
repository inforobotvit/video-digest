import { useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';
const KEY = 'theme';

/** The stored choice, if the reader made one; otherwise the system preference. */
export function currentTheme(): Theme {
  try {
    const stored = localStorage.getItem(KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    /* storage blocked: follow the system */
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new Event('themechange'));
}

/** Two states (brief): the toggle sets the opposite of what is shown and remembers it. */
export function setTheme(theme: Theme) {
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* fine, the choice lives until reload */
  }
  apply(theme);
}

/** Runs once before the first render; index.html does the same inline to avoid a flash. */
export function initTheme() {
  apply(currentTheme());
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', () => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem(KEY);
    } catch {
      /* ignore */
    }
    if (stored !== 'light' && stored !== 'dark') apply(mq.matches ? 'dark' : 'light');
  });
}

export function useTheme(): [Theme, () => void] {
  const [theme, set] = useState<Theme>(() =>
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  );
  useEffect(() => {
    const on = () => set(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light');
    window.addEventListener('themechange', on);
    return () => window.removeEventListener('themechange', on);
  }, []);
  return [theme, () => setTheme(theme === 'dark' ? 'light' : 'dark')];
}
