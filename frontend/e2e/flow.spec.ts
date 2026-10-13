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

// Mock scenario words (src/api/mock.ts): `subs` gives a source with subtitles, transcribe is skipped.
const LINK = 'https://www.youtube.com/watch?v=e2e-subs';
const RESULT_TIMEOUT = 60_000;

test.describe('link → card → run → waiting → result (mock)', () => {
  test('the whole path, three depths, exports and «Мои задачи»', async ({ page }) => {
    await page.goto('/');
    // The limits under the field come from GET /api/limits (the mock answers 200 MB and 90 minutes), not from strings.
    await expect(page.locator('.sources')).toContainText('до 200 МБ');
    await expect(page.locator('.sources')).toContainText('до 90 минут');
    await probeLink(page, LINK);
    const card = page.locator('.card');
    await expect(card.locator('.card__title')).not.toBeEmpty();
    await expect(card.locator('.card__subs')).toContainText('Есть субтитры');
    await expect(page.getByRole('button', { name: T.run })).toBeVisible();
    const title = (await card.locator('.card__title').textContent())!.trim();

    // The preset accordion (step E4): «Просто выжимка» is open, a block can be added; «Лекция» opens with its
    // defaults checked and one can be unchecked – the estimate follows every change.
    const acc = page.getByRole('radiogroup', { name: 'Пресет' });
    await expect(acc.getByRole('radio', { name: /Просто выжимка/ })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    const estimate = acc.locator('.acc__est');
    await expect(estimate).toHaveText(/Готово через ~1 мин/);
    await acc.getByRole('radio', { name: /Лекция/ }).click();
    const glossary = acc.getByRole('checkbox', { name: /Глоссарий/ });
    await expect(glossary).toBeChecked();
    await expect(acc.getByRole('checkbox', { name: /Вопросы для самопроверки/ })).toBeChecked();
    await expect(acc.getByRole('checkbox', { name: /Критика/ })).not.toBeChecked();
    await expect(estimate).toHaveText(/Готово через ~2 мин/); // 60 + 15 + 15 = 90 s
    await glossary.uncheck();
    await expect(estimate).toHaveText(/Готово через ~1 мин/); // 75 s
    await acc.getByRole('checkbox', { name: /Критика/ }).check();
    await expect(estimate).toHaveText(/Готово через ~2 мин/); // 105 s
    // The widget sits in the open row and has its token before the run.
    await expect(
      acc.locator('.acc__item--open .turnstile input[name="cf-turnstile-response"]'),
    ).toHaveValue(/./, {
      timeout: 20_000,
    });

    const id = await runFromForm(page);
    await expectWaiting(page);
    // The job carries the final list: self_check and critique, no glossary.
    await expect(page.locator('.stage', { hasText: 'Дополнительные блоки' })).toContainText(
      'критика, вопросы для самопроверки',
    );
    // Subtitles: the transcribe row is skipped and says so.
    await expect(page.locator('.stage--skipped').first()).toBeVisible();

    await expectResult(page, RESULT_TIMEOUT);
    await expect(page).toHaveURL(new RegExp(`/jobs/${id}$`));
    // Default depth is 5 minutes (2), no param in the URL.
    await expect(depthTabs(page).getByRole('tab', { name: T.depth5 })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    await selectDepth(page, 1);
    await selectDepth(page, 3);
    await selectDepth(page, 2);

    // Exports. The mock builds files in memory; the first pdf request answers 409 by design
    // so the «Повторить» toast can be exercised.
    const md = page.waitForEvent('download');
    await pickExport(page, 'digest.md');
    expect((await md).suggestedFilename()).toMatch(/\.md$/);
    await expect(toasts(page)).toContainText(T.fileReady);

    await pickExport(page, 'digest.pdf');
    const notReady = toasts(page).locator('.toast', { hasText: T.notReady });
    await expect(notReady).toBeVisible();
    const pdf = page.waitForEvent('download');
    await notReady.getByRole('button', { name: T.retry }).click();
    expect((await pdf).suggestedFilename()).toMatch(/\.pdf$/);

    const zip = page.waitForEvent('download');
    await pickExport(page, 'all.zip');
    expect((await zip).suggestedFilename()).toMatch(/\.zip$/);
    await expect(page.getByRole('button', { name: T.download })).toBeEnabled();

    // «Мои задачи» on the home page lists the job as done and leads back to it.
    await page.getByRole('link', { name: T.appName }).click();
    await expect(page).toHaveURL(/\/$/);
    const myJobs = page.getByRole('region', { name: T.myJobs });
    await expect(myJobs).toBeVisible();
    const row = myJobs.locator('.myjob', { hasText: title });
    await expect(row).toContainText('готово');
    await row.getByRole('link').click();
    await expectResult(page, RESULT_TIMEOUT);
    await expect(page).toHaveURL(new RegExp(`/jobs/${id}$`));
  });
});

test.describe('service pages (mock)', () => {
  test('unknown path and unknown job give 404', async ({ page }) => {
    await page.goto('/no-such-page');
    await expect(page.getByRole('heading', { name: T.notFoundTitle })).toBeVisible();
    await expect(page.locator('.svc__code')).toHaveText('404');
    await page.goto('/jobs/missing');
    await expect(page.getByRole('heading', { name: T.notFoundTitle })).toBeVisible();
    await page.getByRole('link', { name: 'На главную' }).click();
    await expect(page).toHaveURL(/\/$/);
  });

  test('/policy opens and links back home', async ({ page }) => {
    await page.goto('/policy');
    await expect(page.getByRole('heading', { name: T.policyTitle })).toBeVisible();
    await page.getByRole('link', { name: T.appName }).click();
    await expect(page.getByRole('textbox', { name: T.linkPlaceholder })).toBeVisible();
  });

  test('the footer leads to the policy from the home page', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Политика данных' }).click();
    await expect(page).toHaveURL(/\/policy$/);
    await expect(page.getByRole('heading', { name: T.policyTitle })).toBeVisible();
  });

  test('contacts: mail and Telegram icons in the header, the author in the footer', async ({
    page,
  }) => {
    for (const path of ['/', '/policy', '/no-such-page']) {
      await page.goto(path);
      const header = page.locator('header');
      await expect(header.getByRole('link', { name: 'Написать на почту' })).toHaveAttribute(
        'href',
        'mailto:tuvitaliy@gmail.com',
      );
      const tg = header.getByRole('link', { name: 'Написать в Telegram' });
      await expect(tg).toHaveAttribute('href', 'https://t.me/mewithrobot');
      await expect(tg).toHaveAttribute('target', '_blank');
    }
    await page.goto('/');
    const author = page
      .locator('footer')
      .getByRole('link', { name: 'Виталий Туров · @mewithrobot' });
    await expect(author).toHaveAttribute('href', 'https://t.me/mewithrobot');
    await expect(author).toHaveAttribute('target', '_blank');
  });
});
