import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ChangesScreen } from './ChangesScreen.tsx';

const CHANGES = [
  {
    id: 'W-07',
    at: '2026-09-21T06:30:00Z',
    actor: 'user',
    parameter: 'Maximale CV-aanvoer',
    old_value: '70 °C',
    new_value: '60 °C',
    reason: 'Aanbeveling B-009',
    finding_id: 'B-009',
    verdict: 'trade_off',
    verdict_text: 'Afweging · terugdraaien',
    rollback_advised: true,
  },
  {
    id: 'W-05',
    at: '2026-09-01T19:00:00Z',
    actor: 'user',
    parameter: 'Nachtverlaging eTwist',
    old_value: '18,0 °C',
    new_value: '17,0 °C',
    reason: '',
    finding_id: null,
    verdict: 'insufficient_evidence',
    verdict_text: 'Onvoldoende bewijs',
    rollback_advised: false,
  },
];

const EVALUATIONS: Record<string, unknown> = {
  'W-07': {
    change_id: 'W-07',
    verdict: 'trade_off',
    verdict_text: 'Afweging · terugdraaien',
    summary: 'Minder starts, maar comfort verslechterd.',
    before: null,
    after: null,
    before_text: '14–20 sep',
    after_text: '22–28 sep',
    conditions: [
      { label: 'Buitentemperatuur gem.', before: '11,2 °C', after: '10,6 °C', comparable: 'yes' },
    ],
    metrics: [
      {
        label: 'CV-starts per uur',
        note: 'per waargenomen uur',
        before: '4,1',
        after: '2,6',
        before_bar_pct: 82,
        after_bar_pct: 52,
        effect_text: 'Beter',
        assessment: 'better',
      },
    ],
  },
  'W-05': {
    change_id: 'W-05',
    verdict: 'insufficient_evidence',
    verdict_text: 'Onvoldoende bewijs',
    summary: 'Perioden niet vergelijkbaar genoeg.',
    before: null,
    after: null,
    before_text: '25–31 aug',
    after_text: '2–8 sep',
    conditions: [
      { label: 'Buitentemperatuur gem.', before: '13,1', after: '17,7', comparable: 'no' },
    ],
    metrics: [],
  },
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(posts: unknown[] = []) {
  const fetchMock = vi.fn<typeof fetch>(async (input) => {
    const req = input as Request;
    const url = new URL(req.url);
    if (req.method === 'POST' && url.pathname === '/api/changes') {
      posts.push(await req.json());
      return json({ ...CHANGES[0], id: 'W-08' }, 201);
    }
    if (url.pathname === '/api/changes') return json({ items: CHANGES });
    if (url.pathname === '/api/findings') return json({ items: [], open_count: 0 });
    const match = /^\/api\/changes\/(.+)\/evaluation$/.exec(url.pathname);
    if (match?.[1]) return json(EVALUATIONS[match[1]]);
    return json({ title: 'Not found', status: 404 }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function renderScreen(path = '/wijzigingen') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <ChangesScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ChangesScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the log and the first change with before/after and comparability', async () => {
    stubApi();
    renderScreen();
    const log = await screen.findByRole('list', { name: 'Wijzigingen' });
    expect(within(log).getAllByRole('listitem')).toHaveLength(2);
    expect(
      await screen.findByRole('heading', { name: 'Maximale CV-aanvoer: 70 °C → 60 °C' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Minder starts, maar comfort verslechterd.')).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Voor en na' })).toBeInTheDocument();
    expect(screen.getByText('Beter')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Vergelijkbaarheid' })).toBeInTheDocument();
  });

  it('selects another change via the log and the URL', async () => {
    stubApi();
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('link', { name: /Nachtverlaging eTwist/ }));
    expect(
      await screen.findByRole('heading', { name: 'Nachtverlaging eTwist: 18,0 °C → 17,0 °C' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Perioden niet vergelijkbaar genoeg.')).toBeVisible();
    expect(screen.queryByRole('heading', { name: 'Voor en na' })).not.toBeInTheDocument();
  });

  it('validates the form and posts a new change', async () => {
    const posts: unknown[] = [];
    stubApi(posts);
    const user = userEvent.setup();
    renderScreen();
    await screen.findByRole('list', { name: 'Wijzigingen' });

    await user.click(screen.getByRole('button', { name: 'Vastleggen' }));
    expect(screen.getByText('Vul de oude waarde in.')).toBeInTheDocument();
    expect(screen.getByLabelText('Oude waarde')).toHaveAttribute('aria-invalid', 'true');
    expect(posts).toHaveLength(0);

    await user.type(screen.getByLabelText('Oude waarde'), '60 °C');
    await user.type(screen.getByLabelText('Nieuwe waarde'), '70 °C');
    await user.click(screen.getByRole('button', { name: 'Vastleggen' }));

    await waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0]).toMatchObject({
      parameter: 'Maximale CV-aanvoer',
      old_value: '60 °C',
      new_value: '70 °C',
      actor: 'user',
    });
    expect(await screen.findByText('Wijziging vastgelegd')).toBeInTheDocument();
  });

  it('shows an empty state with the form still visible', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        const url = new URL((input as Request).url);
        return Promise.resolve(
          url.pathname === '/api/changes'
            ? json({ items: [] })
            : json({ items: [], open_count: 0 }),
        );
      }),
    );
    renderScreen();
    expect(await screen.findByText('Nog geen wijzigingen vastgelegd')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Wijziging vastleggen' })).toBeInTheDocument();
  });

  it('shows an error callout when the log cannot be loaded', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() => Promise.resolve(json({ title: 'Boom', status: 500 }, 500))),
    );
    renderScreen();
    expect(await screen.findByText(/Kon het logboek niet laden/)).toBeInTheDocument();
  });
});
