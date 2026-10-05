import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { components } from '../../api/schema';
import { resetExplainState } from '../../content/useExplain.ts';
import { Overview } from './Overview.tsx';

type OverviewResponse = components['schemas']['OverviewResponse'];

const BASE: OverviewResponse = {
  window: { start: '2026-10-04T04:00:00Z', end: '2026-10-04T10:00:00Z' },
  assessment: {
    level: 'limited',
    reasons: [],
    observed_hours: 6,
    minimum_hours: 6,
    coverage_pct: 92,
  },
  setup: {
    onboarding_done: true,
    flame_mapped: true,
    history_imported: true,
    steps_done: 3,
    steps_total: 3,
  },
  status_card: {
    mode: 'standby',
    title: 'Standby — geen warmtevraag sinds 11:20',
    text: 'Vanochtend stopte de brander vaak binnen 3 minuten.',
  },
  today: {
    range: { start: '2026-10-04T04:00:00Z', end: '2026-10-04T10:00:00Z' },
    ch_cycles: 22,
    short_during_demand: 9,
  },
  next_action: {
    kind: 'recommendation',
    title: 'Max. aanvoertemperatuur terug naar 70 °C',
    text: 'Het terugdraaicriterium is bereikt.',
    finding_id: 'B-011',
    action: { label: 'Open advies', target: '/bevindingen/B-011' },
  },
  kpis: [
    {
      key: 'flow_temperature',
      signal_id: 's1',
      label: 'Aanvoer',
      value: 54.2,
      unit: '°C',
      note_text: 'gemeten · 4 s',
      explanation: 'Server uitleg aanvoer.',
      stale: false,
    },
    {
      key: 'return_temperature',
      signal_id: null,
      label: 'Retour',
      value: null,
      unit: '°C',
      note_text: 'niet gekoppeld',
      explanation: 'Server uitleg retour.',
      stale: false,
    },
  ],
  findings: {
    open_count: 2,
    action_required_count: 1,
    items: [
      {
        id: 'B-011',
        category: 'effect_measurement',
        title: 'Terugdraaicriterium bereikt',
        severity: 'high',
        certainty: 'high',
        relevance: [],
        lifecycle: 'active',
        status: 'rollback',
        status_text: 'Terugdraaicriterium geactiveerd',
        period: { start: '2026-10-01T00:00:00Z' },
        when_text: 'sinds 21 sep',
      },
    ],
  },
  data_quality: {
    coverage_pct: 92,
    level: 'limited',
    text: 'Beperkt. 92 % dekking vandaag.',
    issues: [{ title: 'CAN-uitval', value_text: '10:10–10:40', severity: 'high' }],
  },
  analyses: [
    {
      id: 'cycles',
      name: 'Cycli',
      status: 'available',
      note: 'Vlamstatus 4 s.',
      missing_signals: [],
    },
    {
      id: 'zones',
      name: 'Zones',
      status: 'unavailable',
      note: 'Ontbreekt: klepstatus.',
      missing_signals: [],
    },
  ],
} as unknown as OverviewResponse;

const TIMELINE = {
  range: BASE.window,
  series: {
    start: '2026-10-04T04:00:00Z',
    step_s: 60,
    flow_temperature: [50, 52],
  },
  cycles: [],
  gaps: [],
  changes: [],
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function mockApi(overview: OverviewResponse) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request) => {
      const url = new URL(input.url).pathname;
      if (url.endsWith('/api/overview')) return Promise.resolve(json(overview));
      if (url.endsWith('/api/timeline')) return Promise.resolve(json(TIMELINE));
      return Promise.resolve(json({}));
    }),
  );
}

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderOverview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/overzicht']}>
        <Routes>
          <Route path="overzicht" element={<Overview />} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Overview', () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetExplainState();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders status, action, KPIs, findings, quality and analyses', async () => {
    mockApi(BASE);
    renderOverview();
    expect(await screen.findByText('Standby — geen warmtevraag sinds 11:20')).toBeInTheDocument();
    expect(screen.getByText('Datakwaliteit: beperkt')).toBeInTheDocument();
    expect(screen.getByText('1 vragen om actie')).toBeInTheDocument();
    expect(screen.getByText('Aanbevolen actie')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open advies/ })).toHaveAttribute(
      'href',
      '/bevindingen/B-011',
    );
    // KPI: value with decimal comma; unknown value is a dash, never 0.
    expect(screen.getByText(/54,2/)).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
    // 'uitleg tonen' on: glossary text wins over the server text.
    expect(
      screen.getByText('Temperatuur van het water van de ketel naar radiatoren en vloer.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Hoog')).toBeInTheDocument();
    expect(screen.getByText('CAN-uitval')).toBeInTheDocument();
    expect(await screen.findByText('Niet beschikbaar')).toBeInTheDocument();
    expect(screen.getByText('Beschikbaar')).toBeInTheDocument();
  });

  it('hides KPI explanations when uitleg tonen is off', async () => {
    window.localStorage.setItem('cv-idee.explain', '0');
    mockApi(BASE);
    renderOverview();
    await screen.findByText('Standby — geen warmtevraag sinds 11:20');
    expect(screen.queryByText(/Temperatuur van het water van de ketel/)).not.toBeInTheDocument();
  });

  it('shows no green and no judgement when data is insufficient (FR-36)', async () => {
    const insufficient: OverviewResponse = {
      ...BASE,
      assessment: {
        level: 'insufficient_data',
        observed_hours: 2,
        minimum_hours: 6,
        coverage_pct: 61,
        reasons: [
          {
            code: 'too_few_hours',
            text: 'Pas 2 van 6 uur met gegevens.',
            action: { label: 'Historie importeren', target: '/kwaliteit#import' },
          },
        ],
      },
      setup: { ...BASE.setup, onboarding_done: false, steps_done: 1, history_imported: false },
      next_action: {
        kind: 'setup',
        title: 'Importeer de historie',
        text: 'Dan heb je direct een eerste beoordeling.',
        action: { label: 'Historie importeren', target: '/kwaliteit#import' },
      },
      findings: { open_count: 0, action_required_count: 0, items: [] },
      data_quality: { ...BASE.data_quality, level: 'insufficient_data', coverage_pct: 61 },
    };
    mockApi(insufficient);
    const { container } = renderOverview();
    expect(await screen.findByText('Nog geen beoordeling mogelijk')).toBeInTheDocument();
    expect(screen.getAllByText('Onvoldoende gegevens').length).toBeGreaterThan(0);
    expect(screen.getByText('Pas 2 van 6 uur met gegevens.')).toBeInTheDocument();
    expect(screen.getByText('Eerste stap')).toBeInTheDocument();
    expect(screen.getByText(/Inrichting nog niet af — 1 van 3/)).toBeInTheDocument();
    expect(screen.getByText('Nog geen bevindingen mogelijk')).toBeInTheDocument();
    expect(await screen.findByText('Beschikbaar · wacht op gegevens')).toBeInTheDocument();
    expect(screen.queryByText('Datakwaliteit: beperkt')).not.toBeInTheDocument();
    // No element may use the green tone anywhere on the page.
    const html = container.innerHTML;
    expect(html).not.toContain('--color-green');
    expect(html).not.toContain('--tone-base: var(--color-green');
  });

  it('navigates to the finding when its row is opened', async () => {
    mockApi(BASE);
    renderOverview();
    const user = userEvent.setup();
    const list = await screen.findByText('Terugdraaicriterium bereikt');
    await user.click(list);
    await waitFor(() => {
      expect(screen.getByTestId('where')).toHaveTextContent('/bevindingen/B-011');
    });
  });

  it('shows an error callout when the status cannot be loaded', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response('{}', {
            status: 500,
            headers: { 'content-type': 'application/problem+json' },
          }),
        ),
      ),
    );
    renderOverview();
    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText(/Kon de status niet laden/)).toBeInTheDocument();
  });
});
