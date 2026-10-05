import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProviders } from '../../app/AppProviders.tsx';
import { setViewportWidth } from '../../test/viewport.ts';
import Findings from './Findings.tsx';

function finding(id: string, over: Record<string, unknown> = {}) {
  return {
    id,
    category: 'cycles',
    title: id === 'B-014' ? 'De ketel pendelt tijdens warmtevraag' : `Bevinding ${id}`,
    severity: 'high',
    certainty: 'moderate',
    relevance: ['operational_stability', 'energy'],
    lifecycle: 'active',
    status: 'open',
    status_text: 'Open',
    period: { start: '2026-10-05T04:00:00Z', end: '2026-10-05T08:10:00Z' },
    when_text: 'vandaag 06:00–10:10',
    rule: { id: 'kort-branden', version: '1.3' },
    observation: 'Waarneming van 14 korte cycli.',
    period_text: 'vandaag 06:00–10:10',
    signals_text: 'vlam, aanvoer',
    interpretation: 'Dit kan meerdere oorzaken hebben.',
    hypotheses: [
      {
        number: 1,
        name: 'Te weinig open afgifte',
        evidence_for: 'aanvoer stijgt snel',
        missing: 'zonestatus niet gekoppeld',
        distinguishing_measurement: 'aantal open groepen',
      },
    ],
    evidence: {
      coverage_pct: 98,
      unknown_s: 0,
      excluded_cycles: 0,
      relevant_cycles: 14,
      pattern_cycles: 14,
      repetition_days: 5,
      repetition_window_days: 7,
      missing_signals: [],
      display: {
        coverage: '98 %',
        cycles: '14 van 31',
        repetition: '5 van 7 dagen',
        missing_signals: 'zonestatus',
      },
    },
    recommendation: {
      kind: 'check',
      action: 'Controleer welke circuits open staan.',
      reason: 'Onderscheidt hypothese 1 en 2.',
    },
    no_advice_text: null,
    bundle: [
      { text: '14× brander stopt tijdens warmtevraag', source: 'Stop tijdens vraag · v1.1' },
    ],
    glossary: [],
    timeline_range: { start: '2026-10-05T04:00:00Z', end: '2026-10-05T08:10:00Z' },
    evidence_links: [{ kind: 'cycle', start: '2026-10-05T04:12:00Z', end: '2026-10-05T04:15:00Z' }],
    notes: [],
    ...over,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname + loc.search}</div>;
}

function renderAt(path: string) {
  return render(
    <AppProviders>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/bevindingen" element={<Findings />} />
          <Route path="/bevindingen/:id" element={<Findings />} />
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
}

describe('Findings screen', () => {
  let failStatus = false;
  beforeEach(() => {
    setViewportWidth(1280);
    failStatus = false;
    const statuses = new Map<string, string>();
    vi.stubGlobal(
      'fetch',
      vi.fn((input: Request) => {
        const url = new URL(input.url);
        const detailMatch = /\/api\/findings\/([^/]+)$/.exec(url.pathname);
        if (input.method === 'POST' && url.pathname.endsWith('/status')) {
          if (failStatus) return Promise.resolve(json({ title: 'Kapot', status: 500 }, 500));
          statuses.set('B-014', 'accepted');
          return Promise.resolve(
            json(finding('B-014', { status: 'accepted', status_text: 'Geaccepteerd' })),
          );
        }
        if (detailMatch?.[1]) {
          const id = detailMatch[1];
          return Promise.resolve(
            json(
              finding(id, {
                status: statuses.get(id) ?? 'open',
                status_text: statuses.has(id) ? 'Geaccepteerd' : 'Open',
              }),
            ),
          );
        }
        if (url.pathname.endsWith('/api/findings')) {
          return Promise.resolve(
            json({ items: [finding('B-014'), finding('B-011')], open_count: 2 }),
          );
        }
        return Promise.resolve(json({ title: 'Not found', status: 404 }, 404));
      }),
    );
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders B-014 with observation, hypotheses, advice and bundle', async () => {
    renderAt('/bevindingen/B-014');
    expect(
      await screen.findByRole('heading', {
        level: 2,
        name: 'De ketel pendelt tijdens warmtevraag',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('B-014 · Cycli · vandaag 06:00–10:10')).toBeInTheDocument();
    expect(screen.getByText('Ernst: Hoog')).toBeInTheDocument();
    expect(screen.getByText('Zekerheid: Matig')).toBeInTheDocument();
    expect(screen.getByText('Impact: bedrijfsstabiliteit, energie')).toBeInTheDocument();
    expect(screen.getByText('Waarneming van 14 korte cycli.')).toBeInTheDocument();
    expect(screen.getByText('Te weinig open afgifte')).toBeInTheDocument();
    expect(screen.getByText('Controleer welke circuits open staan.')).toBeInTheDocument();
    expect(screen.getByText('Samengevoegd tot één punt')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Opgeslagen met meetperiode, instellingen en regelversie kort-branden v1.3.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Bevindingen' })).toBeInTheDocument();
  });

  it('selects the finding from the URL', async () => {
    renderAt('/bevindingen/B-011');
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Bevinding B-011' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Bevinding B-011/ })).toHaveAttribute(
      'aria-current',
      'true',
    );
  });

  it('opens the timeline with range and cycle', async () => {
    renderAt('/bevindingen/B-014');
    await userEvent.click(await screen.findByRole('button', { name: /Toon in tijdlijn/ }));
    expect(screen.getByTestId('loc')).toHaveTextContent(
      '/cycli?from=2026-10-05T04%3A00%3A00Z&to=2026-10-05T08%3A10%3A00Z&cycle=2026-10-05T04%3A12%3A00Z',
    );
  });

  it('updates the status optimistically', async () => {
    renderAt('/bevindingen/B-014');
    await userEvent.click(await screen.findByRole('button', { name: /Accepteren/ }));
    await waitFor(() => {
      expect(screen.getAllByText('Geaccepteerd').length).toBeGreaterThan(0);
    });
  });

  it('rolls the status back when saving fails', async () => {
    failStatus = true;
    renderAt('/bevindingen/B-014');
    await userEvent.click(await screen.findByRole('button', { name: /Uitgevoerd/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Kon de status niet opslaan');
    await waitFor(() => {
      expect(screen.queryByText('Uitgevoerd · evaluatie loopt')).not.toBeInTheDocument();
    });
    expect(screen.getAllByText('Open').length).toBeGreaterThan(0);
  });
});
