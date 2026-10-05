import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InstallationScreen } from './InstallationScreen.tsx';

const PROFILE = {
  boiler: {
    model: 'Remeha Calenta Ace',
    control: 'eTwist, modulerend',
    data_source: 'CAN-bus → Home Assistant',
    heat_demand_source: 'eTwist in de woonkamer',
  },
  circuits: [
    {
      id: 'beneden',
      name: 'Beneden',
      kind: 'direct',
      emitter: 'radiator',
      loops: null,
      rooms: ['woonkamer'],
      note: 'Radiatoren hangen direct aan de ketel.',
    },
    {
      id: 'boven',
      name: 'Boven',
      kind: 'mixing_manifold',
      emitter: 'underfloor',
      loops: 5,
      rooms: ['slaapkamer'],
      note: '',
    },
  ],
  rooms: [
    {
      key: 'woonkamer',
      name: 'Woonkamer',
      has_sensor: true,
      is_thermostat: true,
      schedule_text: '07:00–22:30',
      setpoint: 20.5,
      night_setpoint: 17,
    },
    {
      key: 'slaapkamer',
      name: 'Slaapkamer',
      has_sensor: true,
      is_thermostat: false,
      schedule_text: null,
      setpoint: null,
      night_setpoint: null,
    },
  ],
  specifications: [
    {
      key: 'max_ch_flow_temperature',
      label: 'Maximale CV-aanvoer',
      status: 'known',
      value: 60,
      unit: '°C',
      note: 'sinds 21 sep',
    },
    {
      key: 'max_ch_power',
      label: 'Maximaal CV-vermogen',
      status: 'unknown',
      value: null,
      unit: 'kW',
      note: 'nog niet ingevuld',
    },
    {
      key: 'modulation_to_kw',
      label: 'Modulatie → kW',
      status: 'unknown',
      value: null,
      unit: null,
      note: 'geen gecontroleerde omrekening',
    },
    { key: 'gas_price', label: 'Gasprijs', status: 'unknown', value: null, unit: '€/m³', note: '' },
  ],
  revision: 3,
  summary: 'Radiatoren beneden, vloerverwarming boven',
  updated_at: '2026-10-04T10:00:00Z',
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(puts: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const req = input as Request;
      if (req.method === 'PUT') {
        puts.push(await req.json());
        return json(PROFILE);
      }
      return json(PROFILE);
    }),
  );
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <InstallationScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('InstallationScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows boiler, circuits, unknown specs as "Onbekend" and the coming-soon comfort card', async () => {
    stubApi([]);
    renderScreen();
    expect(await screen.findByText('Remeha Calenta Ace')).toBeInTheDocument();
    expect(screen.getByText('Direct op ketel')).toBeInTheDocument();
    expect(screen.getByText('Vloerverwarming · 5 groepen')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    const power = rows.find((r) => within(r).queryByText('Maximaal CV-vermogen'));
    expect(power && within(power).getByText('Onbekend')).toBeInTheDocument();
    const modulation = rows.find((r) => within(r).queryByText('Modulatie → kW'));
    expect(modulation && within(modulation).getByText('Onbekend')).toBeInTheDocument();
    expect(screen.getByText('60 °C')).toBeInTheDocument();
    expect(screen.queryByText(/\d\s?kW/)).not.toBeInTheDocument();
    expect(screen.getByText('Binnenkort')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Instellen' })).toHaveAttribute(
      'href',
      '/instellingen/analyse',
    );
  });

  it('edits a specification through the dialog and sends the revision', async () => {
    const puts: unknown[] = [];
    stubApi(puts);
    const user = userEvent.setup();
    renderScreen();
    await user.click(await screen.findByRole('button', { name: 'Maximaal CV-vermogen bewerken' }));
    const dialog = await screen.findByRole('dialog', { name: 'Maximaal CV-vermogen' });
    await user.selectOptions(within(dialog).getByLabelText('Status'), 'known');
    await user.type(within(dialog).getByLabelText('Waarde (kW)'), '24,5');
    await user.click(within(dialog).getByRole('button', { name: 'Opslaan' }));
    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    const body = puts[0] as {
      revision: number;
      specifications: { key: string; value: unknown; status: string }[];
    };
    expect(body.revision).toBe(3);
    expect(body.specifications.find((s) => s.key === 'max_ch_power')).toMatchObject({
      status: 'known',
      value: 24.5,
    });
  });
});
