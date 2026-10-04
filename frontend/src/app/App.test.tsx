import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { setViewportWidth } from '../test/viewport.ts';
import { App } from './App.tsx';
import { AppProviders } from './AppProviders.tsx';
import { mockShellData } from './shellData.ts';

function renderApp(path = '/') {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <App shellData={mockShellData(new Date('2026-10-04T10:00:00Z'))} />
      </MemoryRouter>
    </AppProviders>,
  );
}

const NAV_LABELS = [
  'Overzicht',
  'Bevindingen',
  'Cycli',
  'Wijzigingen',
  'Advieshistorie',
  'Signalen',
  'Installatie',
  'Gegevenskwaliteit',
  'Meldingen',
  'Analyse-instellingen',
];

describe('App shell', () => {
  beforeEach(() => {
    setViewportWidth(1280);
  });

  it('redirects / to Overzicht and renders the full sidebar', () => {
    renderApp('/');
    const nav = screen.getByRole('navigation', { name: 'Hoofdnavigatie' });
    for (const label of NAV_LABELS) {
      expect(within(nav).getByRole('link', { name: new RegExp(`^${label}`) })).toBeInTheDocument();
    }
    expect(screen.getByRole('heading', { level: 1, name: 'Overzicht' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: /^Overzicht/ })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByText('CV-analyse')).toBeVisible();
    expect(screen.getByText('Thuis · Calenta Ace')).toBeInTheDocument();
    expect(screen.getByText('Analyse')).toBeInTheDocument();
    expect(screen.getByText('Instellingen')).toBeInTheDocument();
    expect(screen.getByText(/Alleen-lezen: deze app stuurt niets aan/)).toBeInTheDocument();
  });

  it('shows nav counts', () => {
    renderApp('/overzicht');
    expect(screen.getByRole('link', { name: 'Bevindingen, 5 open' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Signalen, 9 van 15 gekoppeld' })).toBeInTheDocument();
    expect(screen.getByText('9/15')).toBeInTheDocument();
  });

  it('renders the header with live status, source and date', () => {
    renderApp('/overzicht');
    expect(screen.getByRole('status')).toHaveTextContent('Live · bijgewerkt 12:00');
    expect(screen.getByText('CAN-bus via Home Assistant')).toBeInTheDocument();
  });

  it('navigates between screens', async () => {
    const user = userEvent.setup();
    renderApp('/overzicht');
    await user.click(screen.getByRole('link', { name: /^Signalen/ }));
    expect(screen.getByRole('heading', { level: 1, name: 'Signaalkoppeling' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: 'Analyse-instellingen' }));
    expect(
      screen.getByRole('heading', { level: 1, name: 'Analyse-instellingen' }),
    ).toBeInTheDocument();
  });

  it.each([
    ['/bevindingen', 'Bevindingen'],
    ['/cycli', 'Cycli'],
    ['/wijzigingen', 'Wijzigingen'],
    ['/historie', 'Advieshistorie'],
    ['/installatie', 'Installatieprofiel'],
    ['/kwaliteit', 'Gegevenskwaliteit'],
    ['/meldingen', 'Meldingen'],
    ['/instellingen/analyse', 'Analyse-instellingen'],
  ])('routes %s to its screen', (path, heading) => {
    renderApp(path);
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
  });

  it('shows a not-found state for unknown routes', () => {
    renderApp('/bestaat-niet');
    expect(screen.getByRole('heading', { name: 'Pagina niet gevonden' })).toBeInTheDocument();
  });

  it('collapses to an icon rail below 960px', () => {
    setViewportWidth(959);
    const { container } = renderApp('/overzicht');
    expect(container.querySelector('[data-layout="rail"]')).not.toBeNull();
    // Labels remain available to assistive technology and as tooltips.
    const link = screen.getByRole('link', { name: /^Cycli/ });
    expect(link).toHaveAttribute('title', 'Cycli');
    expect(screen.queryByText(/Alleen-lezen: deze app stuurt niets aan/)).toBeNull();
    // Only the alert badge (open findings) stays visible in the rail.
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.queryByText('9/15')).toBeNull();
  });

  it('uses the full sidebar at 960px', () => {
    setViewportWidth(960);
    const { container } = renderApp('/overzicht');
    expect(container.querySelector('[data-layout="full"]')).not.toBeNull();
  });

  it('renders the component gallery', async () => {
    renderApp('/dev/components');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Componenten' }),
    ).toBeInTheDocument();
  });
});
