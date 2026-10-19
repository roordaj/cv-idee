import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QualityScreen } from './QualityScreen.tsx';

const RANGE = { start: '2026-09-28T10:00:00Z', end: '2026-10-04T10:00:00Z' };
const QUALITY = {
  range: RANGE,
  core_coverage_pct: 96.8,
  coverage: [
    {
      name: 'Vlamstatus',
      signal_ids: ['flame'],
      coverage_pct: 99.1,
      segments: [{ start: '2026-09-30T10:00:00Z', end: '2026-09-30T12:00:00Z', kind: 'stale' }],
    },
    { name: 'Vloertemperatuur', signal_ids: [], coverage_pct: null, segments: [] },
  ],
  events: [
    {
      kind: 'data_gap',
      title: 'Datagat van 2 uur',
      consequence: 'Telt als onbekend.',
      at: '2026-09-30T10:00:00Z',
      recovered: false,
    },
  ],
  mode_share_range: RANGE,
  mode_share: [
    { mode: 'ch', label: 'Cv-bedrijf', minutes: 300, share_pct: 60 },
    { mode: 'standby', label: 'Stand-by', minutes: 200, share_pct: 40 },
  ],
  flame_resolution_s: 4,
  flame_resolution_text: 'Ruim voldoende om cycli korter dan 3 min betrouwbaar te detecteren.',
};
const PERIOD = {
  id: 'p1',
  kind: 'maintenance',
  start: '2026-09-02T07:00:00Z',
  end: '2026-09-02T09:30:00Z',
  description: 'Jaarlijks onderhoud',
  excluded_from: { normal_behaviour: true, comparisons: true, ch_conclusions: true },
  created_at: '2026-09-02T10:00:00Z',
};
const JOB = {
  id: 'i1',
  status: 'fetching',
  range: { start: '2026-09-24T00:00:00Z', end: '2026-10-04T00:00:00Z' },
  blocks_done: 5,
  blocks_total: 10,
  current_block_day: '2026-09-29T00:00:00Z',
  observations_imported: 84212,
  duplicates_skipped: 1304,
  signals: [],
  earliest_available_at: '2026-09-24T00:00:00Z',
  cycles_found: null,
  coverage_pct: null,
  warnings: [],
  errors: [],
  started_at: '2026-10-04T09:12:00Z',
  finished_at: null,
  eta_s: 120,
};
const INSTALLATION = { rooms: [{ key: 'woonkamer', name: 'Woonkamer' }] };

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(posts: unknown[] = [], jobs: unknown[] = [JOB]) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const req = input as Request;
      const url = new URL(req.url);
      if (req.method === 'POST' && url.pathname === '/api/periods') {
        posts.push(await req.json());
        return json({ ...PERIOD, id: 'p2' }, 201);
      }
      if (url.pathname === '/api/quality') return json(QUALITY);
      if (url.pathname === '/api/installation') return json(INSTALLATION);
      if (url.pathname === '/api/periods') return json({ items: [PERIOD] });
      if (url.pathname === '/api/import')
        return json({ items: jobs, earliest_available_at: '2026-09-24T00:00:00Z' });
      if (url.pathname === '/api/import/i1') return json(jobs[0]);
      return json({ title: 'Not found', status: 404 }, 404);
    }),
  );
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <QualityScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('QualityScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders coverage, events, modes and periods', async () => {
    stubApi();
    renderScreen();
    expect(await screen.findByText(/96,8\s?% dekking op ketelsignalen/)).toBeInTheDocument();
    expect(await screen.findByText('Vlamstatus')).toBeInTheDocument();
    expect(screen.getByText('Datagat van 2 uur')).toBeInTheDocument();
    expect(screen.getByText('Cv-bedrijf')).toBeInTheDocument();
    expect(screen.getByText(/Resolutie vlamstatus/)).toBeInTheDocument();
    expect(
      await screen.findByText('Jaarlijks onderhoud · telt niet mee in vergelijkingen'),
    ).toBeInTheDocument();
  });

  it('creates a period through the dialog', async () => {
    const posts: unknown[] = [];
    stubApi(posts);
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('button', { name: /Periode markeren/ }));
    await user.click(screen.getByRole('button', { name: 'Markeren' }));
    expect(await screen.findByText('Kies een soort periode')).toBeInTheDocument();
    await user.click(screen.getByRole('radio', { name: 'Vakantie' }));
    await user.click(screen.getByRole('button', { name: 'Markeren' }));
    await waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0]).toMatchObject({ kind: 'vacation' });
  });

  it('stores a temporary room comfort expectation in a special period', async () => {
    const posts: unknown[] = [];
    stubApi(posts);
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('button', { name: /Periode markeren/ }));
    await user.click(screen.getByRole('radio', { name: 'Vakantie' }));
    await user.selectOptions(
      await screen.findByLabelText('Comfort tijdens periode · Woonkamer'),
      'temporary_target',
    );
    await user.clear(screen.getByLabelText('Tijdelijk doel · Woonkamer'));
    await user.type(screen.getByLabelText('Tijdelijk doel · Woonkamer'), '19.5');
    await user.click(screen.getByRole('button', { name: 'Markeren' }));
    await waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0]).toMatchObject({
      room_overrides: [
        { room_key: 'woonkamer', kind: 'temporary_target', target_temperature_c: 19.5 },
      ],
    });
  });

  it('shows import progress', async () => {
    stubApi();
    renderScreen();
    const bar = await screen.findByRole('progressbar', { name: 'Voortgang import' });
    expect(bar).toHaveAttribute('aria-valuenow', '50');
    expect(screen.getByText(/84\.212 metingen/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Stoppen' })).toBeInTheDocument();
  });
});
