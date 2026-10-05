import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HistoryScreen } from './HistoryScreen.tsx';

const ITEMS = [
  {
    id: 'H-2',
    recorded_at: '2026-10-04T10:00:00Z',
    recommendation: 'Maximale CV-aanvoer verlagen naar 60 °C',
    finding_id: 'B-009',
    observation_period: { start: '2026-09-20T00:00:00Z', end: '2026-10-03T00:00:00Z' },
    settings_text: 'Kortecyclusgrens 10 min',
    rule: { id: 'kort-branden', version: '1.3' },
    status: 'accepted',
    outcome: 'pending',
    status_text: 'Geaccepteerd',
    reasoning: 'Veel korte cycli bij lage warmtevraag.',
    note: 'Eerst proberen',
    rule_now_text: 'Regel is aangescherpt in versie 1.4.',
  },
  {
    id: 'H-1',
    recorded_at: '2026-09-01T10:00:00Z',
    recommendation: 'Pompstand verlagen',
    finding_id: 'B-004',
    observation_period: null,
    settings_text: 'ΔT-doel 20 K',
    rule: { id: 'delta-t', version: '1.0' },
    status: 'rejected',
    outcome: 'undecided',
    status_text: 'Afgewezen',
    reasoning: 'ΔT te klein.',
    note: null,
    rule_now_text: 'Ongewijzigd.',
  },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function renderScreen(items: unknown[] = ITEMS, path = '/historie') {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(() =>
      Promise.resolve(json({ items, total: items.length, limit: 50, offset: 0 })),
    ),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <HistoryScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('HistoryScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('lists advice with status pills and shows the first snapshot', async () => {
    renderScreen();
    const list = await screen.findByRole('list', { name: 'Adviezen' });
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Geaccepteerd')).toBeInTheDocument();
    expect(screen.getByText('Toen vastgelegd')).toBeInTheDocument();
    expect(screen.getByText('kort-branden v1.3')).toBeInTheDocument();
    expect(screen.getByText('Eerst proberen')).toBeInTheDocument();
    expect(screen.getByText(/Regel is aangescherpt/)).toBeInTheDocument();
  });

  it('selects another entry via the list', async () => {
    renderScreen();
    const list = await screen.findByRole('list', { name: 'Adviezen' });
    await userEvent.click(within(list).getByText('Pompstand verlagen'));
    expect(await screen.findByText('delta-t v1.0')).toBeInTheDocument();
    expect(screen.getByText('Ongewijzigd.')).toBeInTheDocument();
  });

  it('honours the selection in the URL', async () => {
    renderScreen(ITEMS, '/historie?advies=H-1');
    expect(await screen.findByText('delta-t v1.0')).toBeInTheDocument();
  });

  it('shows an empty state', async () => {
    renderScreen([]);
    expect(await screen.findByText('Nog geen adviezen')).toBeInTheDocument();
  });

  it('shows an error callout', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(json({ title: 'Boom', status: 500 }, 500))),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <HistoryScreen />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Kon de advieshistorie niet laden/)).toBeInTheDocument();
  });
});
