import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { SignalPanel } from './SignalPanel';
import type { Signal } from './signalFormat';
const signal: Signal = {
  id: 'operating_mode@boiler',
  role: 'operating_mode',
  scope_kind: 'boiler',
  scope_key: null,
  name: 'CV-/tapwatermodus',
  group: 'recommended',
  entity_id: 'sensor.mode',
  unit: null,
  location: null,
  value_kind: 'reported',
  meaning: null,
  needed_for_text: 'Cycli',
  max_age_s: 30,
  expects_regular_updates: false,
  state: 'ok',
  age_s: 0,
  median_update_interval_s: null,
  value_map: null,
};
afterEach(() => vi.unstubAllGlobals());
it('requires provenance and sends only the explicitly confirmed source code table', async () => {
  const writes: unknown[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request) => {
      if (request.method === 'PUT') {
        const body: unknown = await request.json();
        writes.push(body);
      }
      return new Response(JSON.stringify(request.method === 'PUT' ? signal : []), {
        headers: { 'content-type': 'application/json' },
      });
    }),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <SignalPanel signal={signal} signals={[signal]} />
    </QueryClientProvider>,
  );
  const user = userEvent.setup();
  await user.type(
    screen.getByRole('textbox', { name: 'Statuscodes voor deze bron' }),
    '0 = stand-by\n3 = cv\n4 = tapwater\n6 = naloop',
  );
  await user.click(screen.getByRole('button', { name: 'Koppeling opslaan' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Leg de herkomst');
  expect(writes).toEqual([]);
  await user.type(
    screen.getByRole('textbox', { name: 'Herkomst en betekenis van statuscodes' }),
    'AM012: handleiding en gatewayomschrijving; lokale decoder nog niet onafhankelijk gevalideerd.',
  );
  await user.click(screen.getByRole('button', { name: 'Koppeling opslaan' }));
  await waitFor(() => {
    expect(writes).toHaveLength(1);
  });
  expect(writes[0]).toHaveProperty(
    'meaning',
    'AM012: handleiding en gatewayomschrijving; lokale decoder nog niet onafhankelijk gevalideerd.',
  );
  expect(writes[0]).toMatchObject({
    entity_id: 'sensor.mode',
    value_map: { '0': 'standby', '3': 'ch', '4': 'dhw', '6': 'afterrun' },
  });
});
