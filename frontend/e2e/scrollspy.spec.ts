import { expect, test, type Page } from '@playwright/test';
import { T, VIEWPORTS } from './helpers';

/** The chapter the axis marks as being read (aria-current), by its anchor. */
const reading = (page: Page) => page.locator('.toc a[aria-current="true"]');
const mark = (page: Page) => page.locator('.toc__mark');

/** Full transcript so every chapter is taller than the viewport and the page scrolls far. */
const RESULT = '/jobs/sample?depth=3';

test.describe('reading position on the axis (mock)', () => {
  test('desktop: scrollspy follows the top third, a click pins, the mark waits for the player', async ({
    page,
  }) => {
    await page.setViewportSize(VIEWPORTS.desktop);
    await page.goto(RESULT);
    await expect(reading(page)).toHaveAttribute('href', '#chapter-0');
    // The player has not started: only the reading position is on the axis.
    await expect(mark(page)).toHaveCount(0);

    // A chapter heading under the sticky bar is in the top third.
    await page.locator('#chapter-4').evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await expect(reading(page)).toHaveAttribute('href', '#chapter-4');
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(reading(page)).toHaveAttribute('href', '#chapter-0');

    // A timecode click seeks the player (its mark appears) and pins the reading to that chapter,
    // whatever the scroll position.
    await page.locator('#chapter-2 .tc').first().click();
    await expect(mark(page)).toBeVisible();
    await expect(reading(page)).toHaveAttribute('href', '#chapter-2');

    // A table-of-contents pick pins its chapter even when the page cannot scroll it to the top.
    await page.locator('.toc a[href="#chapter-8"]').click();
    await expect(reading(page)).toHaveAttribute('href', '#chapter-8');

    // The reader's own scroll lifts the pin.
    await page.mouse.move(640, 400);
    await page.mouse.wheel(0, -100000);
    await expect(reading(page)).toHaveAttribute('href', '#chapter-0');
    await expect(mark(page)).toBeVisible();
  });

  test('mobile: the sheet opens at the chapter being read and a pick pins it', async ({ page }) => {
    await page.setViewportSize(VIEWPORTS.mobile);
    await page.goto(RESULT);
    await page.locator('#chapter-3').evaluate((el) => el.scrollIntoView({ block: 'start' }));
    await expect(page.locator('.depth__chapter-title')).toHaveText(
      await page.locator('#chapter-3 .chapter__title').innerText(),
    );

    await page.getByRole('button', { name: T.toc }).click();
    const sheet = page.getByRole('dialog', { name: T.toc });
    await expect(sheet.locator('a[aria-current="true"]')).toHaveAttribute('href', '#chapter-3');
    await expect(sheet.locator('.toc__mark')).toHaveCount(0);

    await sheet.locator('a[href="#chapter-6"]').click();
    await expect(sheet).toBeHidden();
    await expect(page.locator('.depth__chapter-title')).toHaveText(
      await page.locator('#chapter-6 .chapter__title').innerText(),
    );
  });
});
