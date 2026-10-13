import { expect, test } from '@playwright/test';
import {
  depthTabs,
  expectResult,
  expectWaiting,
  pickExport,
  probeLink,
  runFromForm,
  selectDepth,
  T,
  toasts,
} from './helpers';

/**
 * The same path against the real API (`npm run e2e:live`, compose from infra/ up). Tagged @live:
 * not part of CI, needs the network and a few minutes. The video is short and carries manual
 * Russian subtitles, so the pipeline skips transcription; override with E2E_LIVE_URL.
 */
const LINK = process.env.E2E_LIVE_URL ?? 'https://www.youtube.com/watch?v=CjznQNTNA-c';
const RESULT_TIMEOUT = 10 * 60_000;

test.describe('live API @live', () => {
  test('link → card → run → waiting → result, exports answer 200, «Мои задачи»', async ({
    page,
  }) => {
    await probeLink(page, LINK);
    const card = page.locator('.card');
    await expect(card.locator('.card__subs')).toContainText('Есть субтитры');
    const title = (await card.locator('.card__title').textContent())!.trim();

    const id = await runFromForm(page);
    await expectWaiting(page);
    await expectResult(page, RESULT_TIMEOUT);
    await expect(page).toHaveURL(new RegExp(`/jobs/${id}$`));

    await expect(depthTabs(page).getByRole('tab', { name: T.depth5 })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await selectDepth(page, 1);
    await selectDepth(page, 3);
    await selectDepth(page, 2);

    for (const format of ['digest.md', 'digest.pdf', 'all.zip'] as const) {
      const response = page.waitForResponse(
        (r) =>
          r.url().endsWith(`/api/jobs/${id}/export/${format}`) && r.request().method() === 'GET',
        { timeout: 60_000 },
      );
      const download = page.waitForEvent('download');
      await pickExport(page, format);
      expect((await response).status(), `${format} status`).toBe(200);
      expect((await download).suggestedFilename()).toMatch(
        new RegExp(`\\.${format.split('.').pop()}$`),
      );
      await expect(toasts(page)).toContainText(T.fileReady);
      await expect(page.getByRole('button', { name: T.download })).toBeEnabled();
    }

    await page.getByRole('link', { name: T.appName }).click();
    const myJobs = page.getByRole('region', { name: T.myJobs });
    const row = myJobs.locator('.myjob', { hasText: title });
    await expect(row).toContainText('готово');
    await row.getByRole('link').click();
    await expectResult(page, 30_000);
  });

  test('unknown job is 404 from the real API', async ({ page }) => {
    await page.goto('/jobs/j_e2e_no_such_job');
    await expect(page.getByRole('heading', { name: T.notFoundTitle })).toBeVisible();
  });

  test('/policy', async ({ page }) => {
    await page.goto('/policy');
    await expect(page.getByRole('heading', { name: T.policyTitle })).toBeVisible();
  });
});
