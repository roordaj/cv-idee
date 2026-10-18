import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { SettingsScreen } from './SettingsScreen';
import { parseNumber, validate } from './schema';

const initial = {
  revision: 'original-revision',
  updated_at: null,
  onboarding_completed_at: null,
  values: {
    short_cycle_min: 3,
    gas_price_eur_per_m3: null,
    show_explanations: true,
    show_requirement_ids: false,
    repetition_days: 2,
    repetition_window_days: 7,
    comparable_weather_c: 2,
    limited_weather_c: 4,
  },
  json_schema: {
    properties: {
      short_cycle_min: {
        title: 'Kortecyclusgrens',
        description: 'Grens voor korte cycli.',
        type: 'number',
        default: 3,
        minimum: 1,
        maximum: 15,
        'x-unit': 'min',
        'x-group': 'short_cycles',
        'x-step': 0.5,
      },
      gas_price_eur_per_m3: {
        title: 'Gasprijs',
        default: null,
        anyOf: [{ type: 'number', minimum: 0.01, maximum: 10 }, { type: 'null' }],
        'x-unit': '€ per m³',
        'x-group': 'costs',
      },
      show_explanations: {
        title: 'Uitleg tonen',
        type: 'boolean',
        default: true,
        'x-group': 'display',
      },
    },
  },
};
function mount(fail = false) {
  const writes: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (request.method === 'PUT') {
        writes.push(await request.json());
        return new Response(JSON.stringify({ title: 'Conflict' }), {
          status: 409,
          headers: { 'content-type': 'application/json' },
        });
      }
      const body =
        path === '/api/settings'
          ? initial
          : path === '/api/signals'
            ? { items: [] }
            : path === '/api/settings/history'
              ? { items: [] }
              : {};
      return new Response(JSON.stringify(body), {
        status: fail && path === '/api/settings' ? 500 : 200,
        headers: { 'content-type': 'application/json' },
      });
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SettingsScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return writes;
}
afterEach(() => vi.unstubAllGlobals());
it('renders schema metadata and saves decimal comma only after confirmation, preserving the revision on conflict', async () => {
  const writes = mount();
  const user = userEvent.setup();
  const field = await screen.findByRole('textbox', { name: 'Kortecyclusgrens in min' });
  expect(field).toHaveValue('3');
  expect(screen.getByText('Grens voor korte cycli.')).toBeInTheDocument();
  await user.clear(field);
  await user.type(field, '4,5');
  await user.click(screen.getByRole('button', { name: 'Opslaan en herberekenen' }));
  expect(writes).toEqual([]);
  await user.click(
    within(screen.getByRole('dialog')).getByRole('button', { name: 'Opslaan en herberekenen' }),
  );
  await waitFor(() => {
    expect(writes).toHaveLength(1);
  });
  expect(writes[0]).toMatchObject({
    revision: 'original-revision',
    values: { short_cycle_min: 4.5, gas_price_eur_per_m3: null },
  });
  expect(await screen.findByText(/Instellingen zijn intussen gewijzigd/)).toBeInTheDocument();
  expect(field).toHaveValue('4,5');
});
it('rejects invalid values without sending a request', async () => {
  const writes = mount();
  const user = userEvent.setup();
  const field = await screen.findByRole('textbox', { name: 'Kortecyclusgrens in min' });
  await user.clear(field);
  await user.type(field, '100');
  await user.tab();
  expect(field).toHaveAttribute('aria-invalid', 'true');
  await user.click(screen.getByRole('button', { name: 'Opslaan en herberekenen' }));
  expect(writes).toEqual([]);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});
it('does not show defaults when loading fails', async () => {
  mount(true);
  expect(await screen.findByText(/Kon de instellingen niet laden/)).toBeInTheDocument();
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
});
it('parses both decimal formats and validates nullable and integer bounds', () => {
  expect(parseNumber('1,25')).toBe(1.25);
  expect(parseNumber('1.25')).toBe(1.25);
  expect(parseNumber('')).toBeNull();
  expect(parseNumber('1e3')).toBeNaN();
  expect(validate('price', '', { anyOf: [{ type: 'number' }, { type: 'null' }] })).toBeNull();
  expect(validate('count', '2,5', { type: 'integer' })).toMatch(/geheel/);
});

it('asks before discarding a draft through an in-app navigation link', async () => {
  mount();
  const user = userEvent.setup();
  const field = await screen.findByRole('textbox', { name: 'Kortecyclusgrens in min' });
  await user.clear(field);
  await user.type(field, '4');
  await user.click(screen.getByRole('link', { name: 'Eerste start openen ›' }));
  expect(screen.getByRole('dialog', { name: 'Wijzigingen niet opgeslagen' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Blijven' }));
  expect(field).toHaveValue('4');
});
