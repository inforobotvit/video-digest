import { expect, test } from '@playwright/test';

// The survey (step E2) on a mock result; `feedback_after` shortens the 45 s wait in the mock only.
test('the survey: offered after the wait and a scroll, sent, remembered; a second answer is refused', async ({
  page,
}) => {
  await page.goto('/jobs/sample?feedback_after=1500');
  await expect(page.getByRole('button', { name: 'Оценить' })).toBeVisible();
  await expect(page.getByRole('dialog', { name: 'Как вам выжимка?' })).toHaveCount(0);
  await page.waitForTimeout(2000);
  // The wait has passed, nothing was done yet: no dialog.
  await expect(page.getByRole('dialog', { name: 'Как вам выжимка?' })).toHaveCount(0);
  await page.mouse.wheel(0, 400);
  const dialog = page.getByRole('dialog', { name: 'Как вам выжимка?' });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText('Не указывайте здесь персональные данные');
  await expect(dialog.getByRole('button', { name: 'Отправить' })).toBeDisabled();
  // Stars (step E4): a click on the fourth lights the first four; the same 1–5 goes to the server.
  const fits = dialog.getByRole('radiogroup', { name: /Возможности сервиса/ });
  await fits.getByRole('radio', { name: '4' }).click();
  await expect(fits.locator('.fb__star--on')).toHaveCount(4);
  await expect(fits.getByRole('radio', { name: '4' })).toHaveAttribute('aria-checked', 'true');
  await expect(fits).toContainText('не согласен');
  await expect(fits).toContainText('полностью согласен');
  await dialog
    .getByRole('radiogroup', { name: /легко пользоваться/ })
    .getByRole('radio', { name: '5' })
    .click();
  await dialog.locator('textarea').fill('Полезно, транскрипт местами короче речи.');
  await expect(dialog.locator('.fb__counter')).toHaveText('40/500');
  await dialog.getByRole('button', { name: 'Отправить' }).click();
  // The dialog's accessible name follows its heading: «Спасибо!» once the answer is in.
  const thanks = page.getByRole('dialog', { name: 'Спасибо!' });
  await expect(thanks).toContainText('Ответ записан');
  await thanks.locator('.fb__thanks').getByRole('button', { name: 'Закрыть' }).click();
  await expect(page.getByRole('button', { name: 'Спасибо за оценку' })).toBeDisabled();

  // Forget the browser's memory of the answer: the server still refuses a second one.
  await page.evaluate(() => {
    Object.keys(localStorage)
      .filter((k) => k.startsWith('feedback:'))
      .forEach((k) => localStorage.removeItem(k));
  });
  await page.reload();
  await page.getByRole('button', { name: 'Оценить' }).click();
  const again = page.getByRole('dialog', { name: 'Как вам выжимка?' });
  await again
    .getByRole('radiogroup', { name: /Возможности сервиса/ })
    .getByRole('radio', { name: '2' })
    .click();
  await again
    .getByRole('radiogroup', { name: /легко пользоваться/ })
    .getByRole('radio', { name: '2' })
    .click();
  await again.getByRole('button', { name: 'Отправить' }).click();
  await expect(page.getByRole('dialog', { name: 'Спасибо!' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Спасибо за оценку' })).toBeDisabled();
});
