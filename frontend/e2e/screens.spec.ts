import { expect, test, type Browser, type Page } from '@playwright/test';
import {
  expectResult,
  expectWaiting,
  probeLink,
  runFromForm,
  selectDepth,
  settle,
  T,
  toggleTheme,
  VIEWPORTS,
  type ViewportName,
} from './helpers';

/**
 * Every screen in both themes and both layouts, saved to e2e/screenshots for a look by eye.
 * Nothing is compared pixel by pixel: the files are committed so a change is visible in the diff
 * and the theme toggle itself is exercised on every screen.
 */
const DIR = 'e2e/screenshots';

type Screen = {
  name: string;
  open: (page: Page) => Promise<void>;
  /** the theme button closes popups (pointerdown outside): reopen them before the shot */
  afterToggle?: (page: Page) => Promise<void>;
};

const SCREENS: Screen[] = [
  {
    name: 'home-empty',
    open: async (page) => {
      await page.goto('/');
      await expect(page.getByRole('textbox', { name: T.linkPlaceholder })).toBeVisible();
    },
  },
  {
    name: 'home-probe-error',
    open: async (page) => {
      await page.goto('/');
      await page
        .getByRole('textbox', { name: T.linkPlaceholder })
        .fill('https://www.youtube.com/watch?v=private-video');
      await page.getByRole('button', { name: T.continue }).click();
      await expect(page.getByRole('alert')).toBeVisible();
    },
  },
  {
    name: 'home-card',
    open: (page) => probeLink(page, 'https://www.youtube.com/watch?v=e2e-shot'),
  },
  {
    name: 'home-settings',
    open: async (page) => {
      await probeLink(page, 'https://www.youtube.com/watch?v=e2e-shot');
      await page.getByRole('radio', { name: /Лекция/ }).click();
    },
  },
  {
    name: 'waiting',
    open: async (page) => {
      // No `subs` in the link: transcribe runs and shows its part counter.
      await probeLink(page, 'https://www.youtube.com/watch?v=e2e-wait');
      await runFromForm(page);
      await expectWaiting(page);
      await expect(page.locator('.stage--running')).toBeVisible();
      await expect(page.locator('.stage--done').nth(1)).toBeVisible({ timeout: 15_000 });
    },
  },
  {
    name: 'job-failed',
    open: async (page) => {
      await probeLink(page, 'https://www.youtube.com/watch?v=e2e-fail');
      await runFromForm(page);
      await expect(page.getByRole('heading', { name: 'Не удалось распознать речь' })).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByRole('button', { name: 'Попробовать снова' })).toBeVisible();
    },
  },
  {
    name: 'home-my-jobs',
    open: async (page) => {
      await page.goto('/');
      await expect(page.getByRole('region', { name: T.myJobs })).toBeVisible();
    },
  },
  {
    name: 'result-depth-1',
    open: async (page) => {
      await page.goto('/jobs/sample');
      await expectResult(page, 20_000);
      await selectDepth(page, 1);
    },
  },
  {
    name: 'result-depth-2',
    open: async (page) => {
      await page.goto('/jobs/sample');
      await expectResult(page, 20_000);
      await selectDepth(page, 2);
    },
  },
  {
    name: 'result-depth-3',
    open: async (page) => {
      await page.goto('/jobs/sample');
      await expectResult(page, 20_000);
      await selectDepth(page, 3);
    },
  },
  {
    name: 'result-download-menu',
    open: async (page) => {
      await page.goto('/jobs/sample');
      await expectResult(page, 20_000);
      await page.getByRole('button', { name: T.download }).click();
      await expect(page.getByRole('menu')).toBeVisible();
    },
    afterToggle: async (page) => {
      await page.getByRole('button', { name: T.download }).click();
      await expect(page.getByRole('menu')).toBeVisible();
    },
  },
  {
    name: 'result-expired',
    open: async (page) => {
      await page.goto('/jobs/expired');
      await expect(page.getByRole('heading', { name: 'Результат удалён' })).toBeVisible();
    },
  },
  {
    name: 'not-found',
    open: async (page) => {
      await page.goto('/jobs/missing');
      await expect(page.getByRole('heading', { name: T.notFoundTitle })).toBeVisible();
    },
  },
  {
    name: 'policy',
    open: async (page) => {
      await page.goto('/policy');
      await expect(page.getByRole('heading', { name: T.policyTitle })).toBeVisible();
    },
  },
];

async function shoot(page: Page, screen: string, viewport: ViewportName, theme: string) {
  await settle(page);
  await page.screenshot({
    path: `${DIR}/${screen}--${viewport}--${theme}.png`,
    fullPage: true,
    animations: 'disabled',
  });
}

async function walk(browser: Browser, viewport: ViewportName) {
  // One context per layout: the theme choice and «Мои задачи» live in localStorage and carry
  // over from screen to screen, which is exactly what a reader sees.
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  const page = await context.newPage();
  for (const screen of SCREENS) {
    await test.step(screen.name, async () => {
      await screen.open(page);
      await toggleTheme(page, 'light');
      await shoot(page, screen.name, viewport, 'light');
      await toggleTheme(page, 'dark');
      await screen.afterToggle?.(page);
      await shoot(page, screen.name, viewport, 'dark');
      await toggleTheme(page, 'light');
    });
  }
  await context.close();
}

test.describe('screens in both themes (mock)', () => {
  test.setTimeout(240_000);
  test('desktop 1280', async ({ browser }) => {
    await walk(browser, 'desktop');
  });
  test('mobile 390', async ({ browser }) => {
    await walk(browser, 'mobile');
  });
});
