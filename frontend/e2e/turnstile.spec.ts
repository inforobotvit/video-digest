import { expect, test } from '@playwright/test';
import { probeLink, runFromForm, expectWaiting, T } from './helpers';

// The mock build uses Cloudflare's test site key (always passes): the widget renders on the run form and the
// run goes through (the test key gives a dummy token without an interactive frame in a headless browser);
// `checkfail` in the link makes the mock answer 403 bot_check_failed.
test.describe('Turnstile on the run form (mock, test key)', () => {
  test('the widget renders on the card and the run goes through', async ({ page }) => {
    await probeLink(page, 'https://www.youtube.com/watch?v=e2e-subs');
    await expect(page.locator('.turnstile input[name="cf-turnstile-response"]')).toHaveValue(/./, {
      timeout: 20_000,
    });
    await runFromForm(page);
    await expectWaiting(page);
  });

  test('403 bot_check_failed shows its text and keeps the retry', async ({ page }) => {
    await probeLink(page, 'https://www.youtube.com/watch?v=e2e-subs-checkfail');
    await page.getByRole('button', { name: T.run }).click();
    const note = page.locator('.settings__error');
    await expect(note).toContainText('Не удалось подтвердить, что запрос из браузера');
    await expect(note.getByRole('button', { name: 'Повторить' })).toBeVisible();
    await expect(page.locator('.turnstile input[name="cf-turnstile-response"]')).toHaveCount(1);
  });
});
