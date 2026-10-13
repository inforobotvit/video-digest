import { expect, test } from '@playwright/test';
import { expectResult, expectWaiting, probeLink, runFromForm } from './helpers';

// Mock scenario word `notices` (src/api/mockJobs.ts): the result carries a transcript_shortened notice.
const LINK = 'https://www.youtube.com/watch?v=e2e-subs-notices';

test('the transcript caveat: a quiet band with the count, places open on request and seek', async ({
  page,
}) => {
  await probeLink(page, LINK);
  await runFromForm(page);
  await expectWaiting(page);
  await expectResult(page, 60_000);
  const band = page.locator('.notices');
  await expect(band).toBeVisible();
  await expect(band).toContainText('Транскрипт мог быть сокращён');
  await expect(band).toContainText(/в[\s\u00a0]\d+[\s\u00a0]местах/);
  await expect(band.locator('.notice__places')).toHaveCount(0);
  await band.getByRole('button', { name: 'Показать места' }).click();
  const codes = band.locator('.notice__places .tc');
  await expect(codes.first()).toBeVisible();
  expect(await codes.count()).toBeGreaterThan(1);
  // A place is a timecode like any other: clicking it stays on the page (the player seeks).
  await codes.first().click();
  await expect(page).toHaveURL(/\/jobs\//);
  await band.getByRole('button', { name: 'Скрыть места' }).click();
  await expect(band.locator('.notice__places')).toHaveCount(0);
});
