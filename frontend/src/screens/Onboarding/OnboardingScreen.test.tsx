import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';
import { OnboardingProvider } from './OnboardingProvider';
import { OnboardingGate, OnboardingScreen } from './OnboardingScreen';
vi.mock('../Quality/ImportCard', () => ({ ImportCard: () => <p>Importpaneel</p> }));
function mount({ connected = true, mapped = true, completed = false, gate = false } = {}) {
  const writes: Record<string, unknown>[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      let body: unknown = {};
      if (request.method === 'PUT') {
        const data = (await request.json()) as Record<string, unknown>;
        writes.push(data);
        body = {
          revision: 'new',
          values: {},
          onboarding_completed_at: data.onboarding_completed_at,
        };
      } else if (path === '/api/settings')
        body = {
          revision: 'revision1',
          values: { min_observation_hours: 6 },
          onboarding_completed_at: completed ? '2026-10-01T00:00:00Z' : null,
        };
      else if (path === '/api/ha/status') body = { configured: true, connected };
      else if (path === '/api/signals')
        body = {
          items: mapped
            ? [
                {
                  id: 'flame@boiler',
                  role: 'flame',
                  entity_id: 'binary_sensor.flame',
                  name: 'Vlamstatus',
                  group: 'required',
                },
              ]
            : [],
        };
      else if (path === '/api/analyses') body = { items: [] };
      return new Response(JSON.stringify(body), {
        headers: { 'content-type': 'application/json' },
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OnboardingProvider>
        <MemoryRouter initialEntries={[gate ? '/overzicht' : '/welkom']}>
          {gate && <OnboardingGate />}
          <Routes>
            <Route path="/welkom" element={<OnboardingScreen />} />
            <Route
              path="/overzicht"
              element={
                <>
                  <h1>Overzicht</h1>
                  <Link to="/welkom">Opnieuw inrichten</Link>
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </OnboardingProvider>
    </QueryClientProvider>,
  );
  return writes;
}
afterEach(() => {
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
it('blocks progression until HA is connected', async () => {
  mount({ connected: false });
  expect(await screen.findByText('Geen verbinding met Home Assistant.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Volgende →' })).toBeDisabled();
});
it('guides mapping and history skip to persisted completion, warning when operating mode is missing', async () => {
  const writes = mount();
  const user = userEvent.setup();
  await screen.findByText('Verbonden met Home Assistant');
  await user.click(screen.getByRole('button', { name: 'Volgende →' }));
  expect(await screen.findByText('binary_sensor.flame')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Volgende →' }));
  await user.click(screen.getByRole('button', { name: 'Toch verder' }));
  expect(screen.getByText('Importpaneel')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Overslaan' }));
  await user.click(screen.getByRole('button', { name: 'Naar het Overzicht' }));
  expect(await screen.findByRole('heading', { name: 'Overzicht' })).toBeInTheDocument();
  expect(typeof writes[0]?.onboarding_completed_at).toBe('string');
  expect(writes[0]).toMatchObject({
    revision: 'revision1',
    values: { min_observation_hours: 6 },
  });
});
it('automatically opens onboarding for a new unmapped installation', async () => {
  mount({ mapped: false, gate: true });
  expect(await screen.findByRole('heading', { name: 'Welkom bij CV-analyse' })).toBeInTheDocument();
});
it('respects persisted completion even if the flame mapping is absent', async () => {
  mount({ mapped: false, completed: true, gate: true });
  await waitFor(() => {
    expect(fetch).toHaveBeenCalled();
  });
  expect(screen.getByRole('heading', { name: 'Overzicht' })).toBeInTheDocument();
});

it('reopens the first connection step after deferral without deleting mappings', async () => {
  mount();
  const user = userEvent.setup();
  await screen.findByText('Verbonden met Home Assistant');
  await user.click(screen.getByRole('button', { name: 'Volgende →' }));
  expect(await screen.findByText('binary_sensor.flame')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Later afmaken ›' }));
  await user.click(screen.getByRole('link', { name: 'Opnieuw inrichten' }));
  expect(
    await screen.findByRole('heading', { name: 'Verbinding met Home Assistant' }),
  ).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Volgende →' }));
  expect(await screen.findByText('binary_sensor.flame')).toBeInTheDocument();
});
