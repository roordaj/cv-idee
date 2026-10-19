import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ZoneAnalysisScreen } from './ZoneAnalysisScreen.tsx';

const START = '2026-10-12T08:00:00Z';
const RESPONSE = {
  start: '2026-10-12T08:00:00Z',
  end: '2026-10-19T08:00:00Z',
  profile_version: '8',
  few_active_zones_max: null,
  short_cycle_threshold_s: 180,
  exclusions: ['Tapwater', 'Onbekende modus'],
  interpretation: 'Zonevraag en gemelde klepstatus zijn aparte meetbronnen.',
  zone_demand: {
    role: 'zone_demand',
    availability: 'limited',
    mapped_zone_keys: ['woonkamer'],
    unmapped_zone_keys: ['slaapkamer'],
    signals: [
      {
        zone_key: 'woonkamer',
        signal_id: 'zone_demand@zone:woonkamer',
        meaning: 'Gerapporteerde vraagstatus',
      },
    ],
    eligible_cycles: 4,
    complete_cycles: 2,
    coverage_pct: 50,
    distribution: [
      {
        active_count: 0,
        cycles: 1,
        short_cycles: 0,
        cycle_starts: [START],
        few_active_zones: null,
      },
    ],
    incomplete_cycles: [
      {
        cycle_start: '2026-10-13T08:00:00Z',
        known_active_count: 0,
        known_zone_keys: ['woonkamer'],
        missing_zone_keys: ['slaapkamer'],
        short: true,
      },
    ],
    unknown_demand_cycles: 0,
    note: 'Warmtevraagstatus ontbreekt of is onbekend.',
  },
  valve_state: {
    role: 'valve_state',
    availability: 'available',
    mapped_zone_keys: ['woonkamer'],
    unmapped_zone_keys: [],
    signals: [],
    eligible_cycles: 4,
    complete_cycles: 4,
    coverage_pct: 100,
    distribution: [
      {
        active_count: 1,
        cycles: 4,
        short_cycles: 2,
        cycle_starts: [START],
        few_active_zones: null,
      },
    ],
    incomplete_cycles: [],
    unknown_demand_cycles: 0,
    note: 'Alle klepstatussen zijn bekend.',
  },
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(zones = [{ key: 'woonkamer', name: 'Woonkamer', circuit_key: 'beneden' }]) {
  const requests: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>((input) => {
      const req = input as Request;
      const url = new URL(req.url);
      requests.push(url.pathname + url.search);
      if (url.pathname === '/api/zones/analysis') return Promise.resolve(json(RESPONSE));
      if (url.pathname === '/api/installation') return Promise.resolve(json({ zones }));
      if (url.pathname === '/api/settings')
        return Promise.resolve(
          json({
            revision: 'rev-1',
            values: { few_active_zones_max: null },
            onboarding_completed_at: null,
          }),
        );
      return Promise.resolve(json({ title: 'Not found', status: 404 }));
    }),
  );
  return requests;
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ZoneAnalysisScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ZoneAnalysisScreen', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps zone demand and valve status separate and links to cycle evidence', async () => {
    stubApi();
    renderScreen();
    expect(await screen.findByRole('heading', { name: 'Zone vraagt warmte' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Klep meldt open' })).toBeInTheDocument();
    expect(screen.getByText(/dekking 50,0%/)).toBeInTheDocument();
    expect(screen.getByText('Onvolledige tellingen')).toBeInTheDocument();
    expect(screen.getByText(/ontbreekt: slaapkamer/)).toBeInTheDocument();
    expect(screen.getByText(/samenhang met korte cycli bewijst geen oorzaak/i)).toBeInTheDocument();
    expect(screen.queryByText(/≤/)).not.toBeInTheDocument();
    const demandTable = screen.getByRole('table', {
      name: 'Zonevraag en korte cycli per zonecount',
    });
    expect(within(demandTable).getByRole('row', { name: /0 1 0/ })).toBeInTheDocument();
    await userEvent.click(within(demandTable).getByText('1 cycli'));
    expect(await within(demandTable).findByRole('link', { name: /cyclusdetails/ })).toHaveAttribute(
      'href',
      expect.stringContaining('/cycli?from='),
    );
  });

  it('identifies missing configuration as unavailable rather than zero active zones', async () => {
    stubApi([]);
    renderScreen();
    expect(await screen.findByText(/Stel eerst zones in/)).toBeInTheDocument();
    expect(screen.getByText(/onbekend niet nul actieve zones/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'installatieprofiel' })).toHaveAttribute(
      'href',
      '/installatie#zones',
    );
  });
});
