import { expect, test } from '@playwright/test';

/**
 * /about/ is a static one-slide page from public/about/ (dark), light.html next to it. Everything it
 * needs ships with the build: no request may leave the origin, and both the QR and the address link
 * to the live site.
 */
const SITE = 'https://digest.inforobot.space';

for (const path of ['/about/', '/about/light.html']) {
  test(`${path} renders from local assets and links to the site`, async ({ page, baseURL }) => {
    const foreign: string[] = [];
    page.on('request', (req) => {
      if (!req.url().startsWith(baseURL!)) foreign.push(req.url());
    });
    await page.goto(path);
    await expect(page).toHaveTitle('Video Digest');
    await expect(page.getByRole('heading', { name: 'Video Digest' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'QR digest.inforobot.space' })).toHaveAttribute(
      'href',
      SITE,
    );
    await expect(
      page.getByRole('link', { name: 'digest.inforobot.space', exact: true }),
    ).toHaveAttribute('href', SITE);
    for (const img of await page.locator('img').all()) {
      await expect(img).toHaveJSProperty('complete', true);
      expect(await img.evaluate((el: HTMLImageElement) => el.naturalWidth)).toBeGreaterThan(0);
    }
    await page.evaluate(() => document.fonts.ready);
    expect(await page.evaluate(() => document.fonts.check('700 128px "IBM Plex Sans"'))).toBe(true);
    expect(await page.evaluate(() => document.fonts.check('30px "IBM Plex Mono"'))).toBe(true);
    expect(foreign).toEqual([]);
  });
}
