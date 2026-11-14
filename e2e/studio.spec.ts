import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('launch a real experiment, inspect decisions, and persist a bookmark', async ({
  page,
  request,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Experiments', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'New experiment' }).click();
  const name = `Browser calibration ${Date.now()}`;
  await page.getByLabel('Experiment name').fill(name);
  await page.getByLabel('Number of games').fill('4');
  await page.getByRole('button', { name: 'Launch experiment' }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  const id = page.url().split('/experiments/')[1];
  await expect
    .poll(async () => {
      const response = await request.get(`/api/experiments/${id}`);
      return (await response.json()).status;
    })
    .toBe('completed');
  const firstGame = page
    .getByRole('row')
    .filter({ has: page.getByRole('button', { name: 'Game 01', exact: true }) });
  await expect(firstGame).toBeVisible();
  await firstGame.getByRole('button', { name: 'Inspect' }).click();
  await expect(page.getByRole('heading', { name: 'Decision timeline' })).toBeVisible();
  await expect(page.getByText('DECISION 1', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Bookmark decision', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Remove bookmark' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Remove bookmark' })).toBeVisible();
  await page.getByRole('button', { name: 'Next decision', exact: true }).click();
  await expect(page.getByText('DECISION 2', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Raw evidence' }).click();
  await expect(page.locator('.raw-evidence')).toContainText('"observation"');
  await page.getByRole('button', { name: 'Final state', exact: true }).click();
  await expect(page.locator('.terminal-detail')).toBeVisible();
  await page.getByRole('button', { name: 'Previous decision', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Decision detail', exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Full trace' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain('replay-');
  const downloadedTrace = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(downloadedTrace.decisions.length).toBeGreaterThan(0);
  expect(downloadedTrace.final_observation.current.result).toBeGreaterThanOrEqual(0);
  await page.getByRole('button', { name: /Legal choices/ }).click();
  await page.screenshot({ path: 'test-results/studio-inspector.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'test-results/studio-inspector-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('deck versions, results, and mobile navigation work', async ({ page }) => {
  await page.goto('/#/decks');
  await expect(page.getByRole('heading', { name: 'Deck lab', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'New deck version' }).click();
  const name = `Deck revision ${Date.now()}`;
  await page.getByLabel('Deck name').fill(name);
  await page.getByLabel('Research note').fill('Browser-tested immutable deck');
  await page.getByRole('button', { name: 'Save deck version' }).click();
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Results', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Experiment comparison' })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('link', { name: 'Experiments', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Experiments', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('button', { name: 'New experiment' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Close dialog' }).click();
  await page.screenshot({ path: 'test-results/studio-mobile.png', fullPage: true });
});
