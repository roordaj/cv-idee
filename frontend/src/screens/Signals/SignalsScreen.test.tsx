import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SignalsScreen } from './SignalsScreen.tsx';

function signal(over: Record<string, unknown>) {
  return {
    role: 'flow_temperature',
    scope_kind: 'boiler',
    scope_key: null,
    group: 'required',
    entity_id: null,
    unit: '°C',
    location: null,
    value_kind: 'measured',
    meaning: null,
    needed_for_text: 'Cycli, Temperaturen',
    max_age_s: 30,
    expects_regular_updates: true,
    state: 'missing',
    age_s: null,
    ...over,
  };
}

const SIGNALS = [
  signal({
    id: 'flame@boiler',
    name: 'Brander/vlam actief',
    role: 'flame',
    unit: null,
    entity_id: 'binary_sensor.remeha_flame',
    state: 'ok',
    age_s: 4,
  }),
  signal({
    id: 'flow@boiler',
    name: 'Ketelaanvoer',
    entity_id: 'sensor.old_flow',
    state: 'stale',
    age_s: 600,
  }),
  signal({ id: 'return@boiler', name: 'Ketelretour' }),
];

const ENTITIES = [
  {
    id: 'sensor.remeha_flow_temp',
    friendly_name: 'Remeha aanvoertemperatuur',
    unit: '°C',
    state: '54.2',
  },
  { id: 'sensor.remeha_pct', friendly_name: 'Remeha modulatie', unit: '%', state: '40' },
];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(puts: { url: string; body: unknown }[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const req = input as Request;
      const url = new URL(req.url);
      if (req.method === 'PUT') {
        puts.push({ url: url.pathname, body: await req.json() });
        return json({ ...SIGNALS[1] });
      }
      if (url.pathname === '/api/signals') return json({ items: SIGNALS, linked: 2, total: 3 });
      if (url.pathname === '/api/ha/entities') return json(ENTITIES);
      return json({ title: 'Not found', status: 404 }, 404);
    }),
  );
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SignalsScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('SignalsScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the grid with age pills and the linked counter', async () => {
    stubApi([]);
    renderScreen();
    expect(await screen.findByText(/2\s+van\s+3\s+signalen gekoppeld/)).toBeInTheDocument();
    const grid = screen.getByRole('list', { name: 'Signalen' });
    expect(within(grid).getByText('4 s')).toBeInTheDocument();
    expect(within(grid).getByText('10 min · te oud')).toBeInTheDocument();
    expect(within(grid).getByText('ontbreekt')).toBeInTheDocument();
    expect(screen.getByText(/Let op bij interpretatie/)).toBeInTheDocument();
  });

  it('searches the entity picker, selects an entity and saves the mapping', async () => {
    const puts: { url: string; body: unknown }[] = [];
    stubApi(puts);
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('button', { name: /Ketelaanvoer/ }));
    await user.click(screen.getByRole('button', { name: 'Andere entiteit kiezen' }));
    const dialog = await screen.findByRole('dialog', { name: 'Entiteit kiezen' });
    await user.click(within(dialog).getByRole('radio', { name: 'Alle entiteiten' }));
    await user.type(within(dialog).getByRole('combobox'), 'modulatie');
    expect(within(dialog).getAllByRole('option')).toHaveLength(1);
    await user.clear(within(dialog).getByRole('combobox'));
    await user.type(within(dialog).getByRole('combobox'), 'AANVOER');
    await user.click(
      await within(dialog).findByRole('option', { name: /sensor.remeha_flow_temp/ }),
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Home Assistant-entiteit')).toHaveValue('sensor.remeha_flow_temp');
    await user.click(screen.getByRole('button', { name: 'Koppeling opslaan' }));
    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    expect(puts[0]?.url).toBe('/api/signals/flow%40boiler');
    expect(puts[0]?.body).toMatchObject({
      entity_id: 'sensor.remeha_flow_temp',
      unit: '°C',
      expects_regular_updates: true,
      max_age_s: 30,
    });
    expect(await screen.findByText('Opgeslagen')).toBeInTheDocument();
  });

  it('blocks saving when the entity unit does not fit the signal', async () => {
    stubApi([]);
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('button', { name: /Ketelaanvoer/ }));
    await user.click(screen.getByRole('button', { name: 'Andere entiteit kiezen' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('radio', { name: 'Alle entiteiten' }));
    await user.click(await within(dialog).findByRole('option', { name: /sensor.remeha_pct/ }));
    expect(
      screen.getByText('Deze entiteit meet in %, maar dit signaal verwacht °C.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Koppeling opslaan' })).toBeDisabled();
  });
});
