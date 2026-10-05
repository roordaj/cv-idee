import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NotificationsScreen } from './NotificationsScreen.tsx';

const POLICY = {
  channels: { high: 'direct', medium: 'daily_digest', low: 'weekly_report', info: 'none' },
  bundle_related: true,
  renotify_on_worsening: false,
  recovery_text: '3 dagen zonder patroon, bij vergelijkbaar weer en ≥ 90 % gegevens',
};

const EXPORT = {
  transport: 'mqtt',
  connected: true,
  updated_at: '2026-10-04T10:00:00Z',
  entities: [
    {
      entity_id: 'sensor.cv_analyse_starts_per_uur',
      state: '2.4',
      display: '2,4 /u',
      unit: '/u',
    },
  ],
};

const SENT = {
  items: [
    {
      id: 'N-1',
      kind: 'finding_new',
      title: 'Korte cycli',
      detail: 'één melding voor 14 cycli',
      finding_id: 'B-001',
      sent_at: '2026-10-04T07:15:00Z',
      channel: 'direct',
      status: 'sent',
    },
  ],
  total: 1,
  limit: 5,
  offset: 0,
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function stubApi(puts: unknown[] = [], exportBody: unknown = EXPORT) {
  vi.stubGlobal(
    'fetch',
    vi.fn<typeof fetch>(async (input) => {
      const req = input as Request;
      const url = new URL(req.url);
      if (url.pathname === '/api/notifications/policy') {
        if (req.method === 'PUT') {
          const body: unknown = await req.json();
          puts.push(body);
          return json({ ...POLICY, ...(body as object) });
        }
        return json(POLICY);
      }
      if (url.pathname === '/api/notifications') return json(SENT);
      if (url.pathname === '/api/ha/export') return json(exportBody);
      return json({ title: 'Not found', status: 404 }, 404);
    }),
  );
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <NotificationsScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('NotificationsScreen', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders policy, recovery summary, HA export and recent notifications', async () => {
    stubApi();
    renderScreen();
    expect(await screen.findByText('Kanaal per ernst')).toBeInTheDocument();
    expect(screen.getByText(POLICY.recovery_text)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Aanpassen in Analyse-instellingen/ })).toHaveAttribute(
      'href',
      '/instellingen/analyse',
    );
    expect(await screen.findByText('sensor.cv_analyse_starts_per_uur')).toBeInTheDocument();
    expect(screen.getByText('2,4 /u')).toBeInTheDocument();
    expect(screen.getByText(/MQTT · verbonden/)).toBeInTheDocument();
    const recent = await screen.findByRole('list', { name: 'Recent verstuurd' });
    expect(within(recent).getByText('Korte cycli')).toBeInTheDocument();
  });

  it('saves a channel change through the policy endpoint', async () => {
    const puts: unknown[] = [];
    stubApi(puts);
    renderScreen();
    const group = await screen.findByRole('radiogroup', { name: 'Kanaal voor ernst Hoog' });
    await userEvent.click(within(group).getByRole('radio', { name: 'Weekrapport' }));
    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    expect(puts[0]).toMatchObject({
      channels: { high: 'weekly_report', medium: 'daily_digest' },
      bundle_related: true,
    });
  });

  it('saves a noise-suppression toggle', async () => {
    const puts: unknown[] = [];
    stubApi(puts);
    renderScreen();
    await userEvent.click(await screen.findByRole('switch', { name: /Opnieuw melden/ }));
    await waitFor(() => {
      expect(puts).toHaveLength(1);
    });
    expect(puts[0]).toMatchObject({ renotify_on_worsening: true, bundle_related: true });
  });

  it('warns when the HA export is not connected', async () => {
    stubApi([], { ...EXPORT, connected: false, entities: [] });
    renderScreen();
    expect(await screen.findByText(/Niet verbonden met de MQTT-broker/)).toBeInTheDocument();
  });
});
