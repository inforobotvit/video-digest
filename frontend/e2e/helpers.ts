import { expect, type Locator, type Page } from '@playwright/test';

/** Interface strings the tests look for. Kept here rather than imported from src: the tests see the app as a user does. */
export const T = {
  linkPlaceholder: 'Ссылка на видео',
  continue: 'Продолжить',
  run: 'Запустить',
  processing: 'Обрабатываем',
  depth: 'Глубина',
  depth1: /1 мин/,
  depth5: /5 мин/,
  depthAll: /^Всё/,
  depthHint1: 'TL;DR и заголовки глав',
  depthHint5: /тезис/,
  depthHintAll: /транскрипт/,
  download: 'Скачать',
  preparing: 'Готовим…',
  exportTitles: { 'digest.md': 'Выжимка', 'digest.pdf': 'PDF', 'all.zip': 'Всё архивом' } as const,
  fileReady: /^Файл готов/,
  notReady: 'Файл ещё готовится',
  retry: 'Повторить',
  myJobs: 'Мои задачи',
  notFoundTitle: 'Такой задачи нет или результат уже удалён',
  policyTitle: 'Как сервис обрабатывает данные',
  themeDark: 'Тёмная тема',
  themeLight: 'Светлая тема',
  appName: 'Video Digest',
  toc: 'Оглавление',
};

export const VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 },
} as const;
export type ViewportName = keyof typeof VIEWPORTS;

/** Home page: paste the link, wait for the source card (mock probe answers in ~1.2 s, the real one longer). */
export async function probeLink(page: Page, url: string): Promise<void> {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: T.linkPlaceholder });
  await input.fill(url);
  await page.getByRole('button', { name: T.continue }).click();
  await expect(page.locator('.card')).toBeVisible({ timeout: 60_000 });
}

/** «Запустить» on the form under the card → the waiting page. Returns the job id from the URL. */
export async function runFromForm(page: Page): Promise<string> {
  await page.getByRole('button', { name: T.run }).click();
  await page.waitForURL(/\/jobs\/[A-Za-z0-9_-]+$/);
  return page.url().split('/jobs/')[1];
}

/** Waiting page markers: the heading and at least one stage row. */
export async function expectWaiting(page: Page): Promise<void> {
  await expect(page.getByRole('heading', { name: T.processing })).toBeVisible();
  await expect(page.locator('.stages .stage').first()).toBeVisible();
}

export function depthTabs(page: Page): Locator {
  return page.getByRole('tablist', { name: T.depth });
}

/**
 * The result page is there once the depth switch is on screen. A failed job shows the error view
 * instead; the test fails right away with the stage and code from the grey line rather than waiting.
 */
export async function expectResult(page: Page, timeout: number): Promise<void> {
  const failed = page.locator('.jerr__code, .page__code');
  await expect(depthTabs(page).or(failed).first()).toBeVisible({ timeout });
  if (await failed.count())
    throw new Error(`job failed: ${(await failed.first().textContent())?.trim()}`);
}

/** Switch to a depth and check the page followed: tab state, URL param (2 is the default and has none), hint. */
export async function selectDepth(page: Page, depth: 1 | 2 | 3): Promise<void> {
  const name = depth === 1 ? T.depth1 : depth === 2 ? T.depth5 : T.depthAll;
  const tab = depthTabs(page).getByRole('tab', { name });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-selected', 'true');
  const param = new URL(page.url()).searchParams.get('depth');
  expect(param).toBe(depth === 2 ? null : String(depth));
  const hint = page.locator('.depth__hint');
  await expect(hint).toHaveText(
    depth === 1 ? T.depthHint1 : depth === 2 ? T.depthHint5 : T.depthHintAll,
  );
}

/** Open «Скачать» and pick a format; the caller decides what to wait for. */
export async function pickExport(page: Page, format: keyof typeof T.exportTitles): Promise<void> {
  await page.getByRole('button', { name: T.download }).click();
  await page.getByRole('menuitem', { name: T.exportTitles[format] }).click();
}

export function toasts(page: Page): Locator {
  return page.getByRole('status');
}

export function themeButton(page: Page): Locator {
  return page.getByRole('button', { name: /^(Тёмная|Светлая) тема$/ });
}

/** Flip the theme through the header button and check the html attribute followed. */
export async function toggleTheme(page: Page, to: 'light' | 'dark'): Promise<void> {
  const html = page.locator('html');
  const current = await html.getAttribute('data-theme');
  if (current === to) return;
  await themeButton(page).click();
  await expect(html).toHaveAttribute('data-theme', to);
  await expect(themeButton(page)).toHaveAttribute(
    'aria-label',
    to === 'dark' ? T.themeLight : T.themeDark,
  );
}

/** Lets fonts and the first paint settle so a screenshot is not caught mid-transition. */
export async function settle(page: Page): Promise<void> {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
}
