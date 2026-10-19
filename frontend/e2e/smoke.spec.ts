import { expect, test } from '@playwright/test';

const screens = [
  ['Overzicht', 'Overzicht'],
  ['Bevindingen', 'Bevindingen'],
  ['Cycli', 'Cycli'],
  ['Wijzigingen', 'Wijzigingen'],
  ['Advieshistorie', 'Advieshistorie'],
  ['Signalen', 'Signaalkoppeling'],
  ['Installatie', 'Installatieprofiel'],
  ['Gegevenskwaliteit', 'Gegevenskwaliteit'],
  ['Meldingen', 'Meldingen'],
  ['Analyse-instellingen', 'Analyse-instellingen'],
] as const;

test('loads every screen through the simulated Home Assistant ingress path', async ({ page }) => {
  await page.goto('overzicht');
  await expect(page.getByRole('heading', { name: 'Overzicht', level: 1 })).toBeVisible();
  const navigation = page.getByRole('navigation', { name: 'Hoofdnavigatie' });

  for (const [label, heading] of screens.slice(1)) {
    await navigation.getByRole('link', { name: new RegExp(label) }).click();
    await expect(page.getByRole('heading', { name: heading, level: 1 })).toBeVisible();
  }

  const response = await page.request.get('api/status');
  expect(response.ok()).toBeTruthy();
  await expect(page.locator('base')).toHaveAttribute('href', '/api/hassio_ingress/e2e-token/');
});

test('opens a finding in its cycle timeline and saves its status', async ({ page }) => {
  await page.goto('bevindingen');
  await page.getByRole('button', { name: /Herhaald kort branden/ }).click();
  await expect(page.getByRole('heading', { name: /Herhaald kort branden/ })).toBeVisible();

  await page.getByRole('button', { name: 'Toon in tijdlijn' }).click();
  await expect(page).toHaveURL(/\/cycli\?from=/);
  await expect(page.getByRole('heading', { name: 'Cycli', level: 1 })).toBeVisible();

  await page.goBack();
  await page.getByRole('button', { name: /Herhaald kort branden/ }).click();
  await page.getByRole('button', { name: 'Accepteren' }).click();
  await expect(
    page.getByRole('region', { name: 'Bevinding' }).getByText('Geaccepteerd'),
  ).toBeVisible();
});

test('records a change and saves a signal mapping', async ({ page }) => {
  await page.goto('wijzigingen');
  await page.getByLabel('Tijdstip (Europe/Amsterdam)').fill('2026-10-03T12:00');
  await page.getByLabel('Oude waarde').fill('60 °C');
  await page.getByLabel('Nieuwe waarde').fill('65 °C');
  await page.getByLabel('Reden').fill('E2E-smoketest');
  await page.getByRole('button', { name: 'Vastleggen' }).click();
  await expect(page.getByRole('status').getByText('Wijziging vastgelegd')).toBeVisible();

  await page.goto('signalen');
  await page.getByRole('button', { name: /Brander\/vlam actief/ }).click();
  await page.getByRole('button', { name: 'Koppeling opslaan' }).click();
  await expect(page.getByRole('status').getByText('Opgeslagen')).toBeVisible();
});
