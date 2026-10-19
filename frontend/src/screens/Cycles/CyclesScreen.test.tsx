import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CyclesScreen } from './CyclesScreen.tsx';

const RANGE = { start: '2026-10-04T04:00:00Z', end: '2026-10-04T10:00:00Z' };

const BASE = {
  mode: 'ch',
  flow_setpoint: 45,
  short_during_demand: false,
  duration_is_lower_bound: false,
  max_flow_temperature: 48.5,
  mean_modulation_pct: 32,
};
const CYCLES = [
  {
    ...BASE,
    number: 1,
    start: '2026-10-04T04:10:00Z',
    end: '2026-10-04T04:25:00Z',
    duration_s: 900,
    end_reason: 'demand_ended',
    classification: 'normal',
  },
  {
    ...BASE,
    number: 2,
    start: '2026-10-04T05:00:00Z',
    end: '2026-10-04T05:02:00Z',
    duration_s: 120,
    end_reason: 'stop_during_demand',
    short_during_demand: true,
    classification: 'short',
  },
  {
    ...BASE,
    number: 3,
    start: '2026-10-04T08:10:00Z',
    end: null,
    duration_s: 600,
    duration_is_lower_bound: true,
    end_reason: 'data_gap',
    classification: 'incomplete',
  },
];

const SUMMARY = {
  observed_hours: 5.5,
  starts_per_hour: 0.4,
  ch_cycles: 3,
  dhw_cycles: 1,
  short_during_demand: 1,
  short_cycle_threshold_s: 180,
  median_burn_s: 600,
  mean_burn_s: 540,
  median_pause_s: 1500,
  total_burn_s: 7800,
  incomplete_cycles: 1,
};

const TIMELINE = {
  range: RANGE,
  series: {
    start: RANGE.start,
    step_s: 60,
    flow_temperature: [],
    return_temperature: [],
    flow_setpoint: [],
    modulation_pct: [],
  },
  modes: [],
  heat_demand: [],
  cycles: CYCLES,
  gaps: [],
  changes: [],
  last_change_before: null,
  periods: [],
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>((input) => {
      const url = new URL((input as Request).url);
      if (url.pathname === '/api/timeline') return Promise.resolve(json(TIMELINE));
      if (url.pathname === '/api/cycles')
        return Promise.resolve(
          json({
            range: RANGE,
            summary: SUMMARY,
            items: CYCLES,
            total: 3,
            limit: 500,
            offset: 0,
          }),
        );
      return Promise.resolve(json({ title: 'Not found', status: 404 }));
    }),
  );
}

function renderScreen(path = '/cycli') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <CyclesScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CyclesScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders KPIs, chart and the cycle table from the API', async () => {
    stubApi();
    renderScreen();
    expect(await screen.findByText('Starts per uur (CV)')).toBeInTheDocument();
    expect(screen.getByText('0,4')).toBeInTheDocument();
    expect(screen.getByText('over 5,5 u met gegevens')).toBeInTheDocument();
    expect(screen.getByText('+ 1 tapwater (uitgesloten)')).toBeInTheDocument();
    expect(screen.getByText('korter dan 3:00')).toBeInTheDocument();
    expect(screen.getByText('standby niet meegeteld')).toBeInTheDocument();
    expect(screen.getByText('1 cyclus onvolledig')).toBeInTheDocument();
    expect(await screen.findByRole('group', { name: /Tijdlijn met 3 cycli/ })).toBeInTheDocument();
    const table = await screen.findByRole('table', { name: 'Alle cycli' });
    expect(within(table).getAllByRole('row')).toHaveLength(4);
    expect(screen.getByRole('radio', { name: '6 uur', checked: true })).toBeInTheDocument();
  });

  it('links to the last change before the selected time window', async () => {
    const timeline = {
      ...TIMELINE,
      last_change_before: {
        id: 'W-07',
        at: '2026-09-21T06:30:00Z',
        parameter: 'Maximale CV-aanvoer',
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        const url = new URL((input as Request).url);
        return Promise.resolve(
          json(url.pathname === '/api/timeline' ? timeline : { items: CYCLES, summary: SUMMARY }),
        );
      }),
    );
    renderScreen();
    const link = await screen.findByRole('link', { name: /W-07.*Maximale CV-aanvoer/ });
    expect(link.getAttribute('href')).toBe('/wijzigingen?wijziging=W-07');
  });

  it('formats an incomplete cycle with unknown end and lower-bound duration', async () => {
    stubApi();
    renderScreen();
    const table = await screen.findByRole('table', { name: 'Alle cycli' });
    const row = within(table).getAllByRole('row')[3];
    expect(row).toBeDefined();
    const cells = within(row as HTMLElement).getAllByRole('cell');
    expect(cells[2]).toHaveTextContent('onbekend');
    expect(cells[3]).toHaveTextContent('≥ 10:00');
    expect(cells[5]).toHaveTextContent('Datagat');
    expect(cells[8]).toHaveTextContent('Onvolledig');
  });

  it('syncs selection between table rows and chart bars', async () => {
    stubApi();
    const user = userEvent.setup();
    renderScreen();
    const table = await screen.findByRole('table', { name: 'Alle cycli' });
    await user.click(within(table).getAllByRole('row')[2] as HTMLElement);
    expect(await screen.findByTestId('cycle-2')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('cycle-1')).toHaveAttribute('aria-pressed', 'false');
    await user.click(screen.getByTestId('cycle-1'));
    expect(screen.getByTestId('cycle-1')).toHaveAttribute('aria-pressed', 'true');
    expect(within(table).getAllByRole('row')[1]).toHaveAttribute('aria-selected', 'true');
    expect(within(table).getAllByRole('row')[2]).toHaveAttribute('aria-selected', 'false');
  });

  it('selects the cycle from the deep link', async () => {
    stubApi();
    renderScreen('/cycli?from=2026-10-04T04:00:00Z&to=2026-10-04T10:00:00Z&cycle=3');
    expect(await screen.findByTestId('cycle-3')).toHaveAttribute('aria-pressed', 'true');
    const table = await screen.findByRole('table', { name: 'Alle cycli' });
    expect(within(table).getAllByRole('row')[3]).toHaveAttribute('aria-selected', 'true');
  });
});
