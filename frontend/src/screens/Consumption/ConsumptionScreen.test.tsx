import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConsumptionScreen } from './ConsumptionScreen.tsx';

const OBSERVATION = {
  start: '2026-10-13T22:00:00Z',
  end: '2026-10-20T22:00:00Z',
};
const REFERENCE = {
  start: '2026-10-06T22:00:00Z',
  end: '2026-10-13T22:00:00Z',
};

const context = {
  outdoor_temperature_c: 9.2,
  outdoor_coverage_pct: 95,
  room_setpoints_c: { woonkamer: 20 },
  heating_runtime_hours: 18,
  heat_demand_hours: 32,
  dhw_runtime_hours: 1.2,
  zone_use: 'unknown',
  special_periods: [],
};

function candidate(range: typeof REFERENCE, over: Record<string, unknown> = {}) {
  return {
    range,
    status: 'limited',
    reasons: ['use_context_unknown'],
    counter_start: 100,
    counter_end: 104,
    consumption_m3: 4,
    meter_scope: 'boiler_only',
    meter_entity_id: 'sensor.gas_total',
    unit: 'm³',
    mapping_revision: 1,
    coverage_pct: 96,
    consumption_availability: 'available',
    cost_availability: 'unavailable',
    context,
    ...over,
  };
}

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ConsumptionScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConsumptionScreen', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows honest unavailable state when there is no gas meter or candidate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>(() =>
        Promise.resolve(
          json({
            observation: OBSERVATION,
            observation_data: candidate(OBSERVATION, {
              status: 'unavailable',
              reasons: ['no_meter'],
              counter_start: null,
              counter_end: null,
              consumption_m3: null,
              meter_scope: 'unknown',
              meter_entity_id: null,
              unit: null,
              mapping_revision: null,
              coverage_pct: null,
              consumption_availability: 'unavailable',
            }),
            status: 'unavailable',
            reasons: ['no_meter', 'no_valid_period'],
            candidates: [],
            consumption_availability: 'unavailable',
            efficiency_availability: 'unavailable',
            cost_availability: 'unavailable',
          }),
        ),
      ),
    );
    renderScreen();

    expect(await screen.findByText('Geen vergelijkbare periode beschikbaar')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Gemeten gas' })).toBeInTheDocument();
    expect(screen.getByText('Niet gekoppeld of geen meetpunten')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Bekijk installatieprofiel' })).toHaveAttribute(
      'href',
      '/installatie',
    );
    expect(
      screen.getByRole('img', {
        name: 'Schematische meterreeks met onbekend interval en tellerreset; geen meetreeks',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('table', { name: 'Context bij geselecteerde perioden' })).toBeVisible();
    expect(screen.queryByText(/0,000 m³/)).not.toBeInTheDocument();
  });

  it('lets the user choose a candidate and shows both raw periods and limited-use context', async () => {
    const requests: Request[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((input) => {
        const request = input instanceof Request ? input : new Request(input);
        requests.push(request);
        if (new URL(request.url).pathname.endsWith('/candidates')) {
          return Promise.resolve(
            json({
              observation: OBSERVATION,
              observation_data: candidate(OBSERVATION, {
                counter_start: 108,
                counter_end: 113,
                consumption_m3: 5,
              }),
              status: 'limited',
              reasons: [],
              candidates: [candidate(REFERENCE)],
              consumption_availability: 'available',
              efficiency_availability: 'unavailable',
              cost_availability: 'unavailable',
            }),
          );
        }
        return Promise.resolve(
          json({
            reference: candidate(REFERENCE),
            observation: candidate(OBSERVATION, {
              counter_start: 108,
              counter_end: 113,
              consumption_m3: 5,
            }),
            status: 'limited',
            reasons: ['use_context_unknown'],
            difference_m3: 1,
            basis: 'Ruwe meterstanden; geen weerscorrectie.',
            consumption_availability: 'available',
            efficiency_availability: 'unavailable',
            cost_availability: 'unavailable',
          }),
        );
      }),
    );
    const user = userEvent.setup();
    renderScreen();

    const picker = await screen.findByRole('combobox', { name: 'Historische referentieperiode' });
    await user.selectOptions(picker, `${REFERENCE.start}/${REFERENCE.end}`);
    await user.click(screen.getByRole('button', { name: 'Vergelijk geselecteerde periode' }));

    expect(
      await screen.findByRole('heading', { name: 'Geselecteerde periodevergelijking' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('5,000 m³')).toBeInTheDocument();
    expect(screen.getByText('1,000 m³')).toBeInTheDocument();
    const contextTable = screen.getByRole('table', { name: 'Context bij geselecteerde perioden' });
    expect(
      within(contextTable).getByRole('row', { name: /CV-bedrijfsduur 18,0 u 18,0 u/ }),
    ).toBeVisible();
    expect(screen.getAllByText('Koken, tapwater of ander gebruik onbekend').length).toBeGreaterThan(
      0,
    );
    await waitFor(async () => {
      const post = requests.find((request) => request.method === 'POST');
      expect(post).toBeDefined();
      expect(await post?.clone().json()).toMatchObject({
        observation: {
          start: new Date(OBSERVATION.start).toISOString(),
          end: new Date(OBSERVATION.end).toISOString(),
        },
        reference: REFERENCE,
      });
    });
  });
});
