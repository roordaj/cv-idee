import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ReportsScreen } from './ReportsScreen.tsx';

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

describe('ReportsScreen', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('previews one snapshot and links every download to that snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn<typeof fetch>((request) => {
        const url = new URL(request instanceof Request ? request.url : String(request));
        if (url.pathname.endsWith('/snapshots')) {
          return Promise.resolve(
            json({
              id: 'snapshot-1',
              report: {
                kind: 'day',
                period: { start: '2026-10-18T22:00:00Z', end: '2026-10-19T22:00:00Z' },
                generated_at: '2026-10-20T08:00:00Z',
                quality: { coverage: [{ name: 'Vlam', coverage_pct: 95 }] },
                cycle_summary: { ch_cycles: 3, dhw_cycles: 1 },
                findings: [],
                open_advice: [],
                status_changes: [],
                changes: [],
                has_more_cycles: false,
              },
            }),
          );
        }
        if (url.pathname.endsWith('/delivery-status')) {
          return Promise.resolve(
            json({ enabled: false, available: false, status: null, error: null }),
          );
        }
        throw new Error(`Unexpected report request: ${url.pathname}`);
      }),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ReportsScreen />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText(/4 cycli · 0 bevindingen · 0 wijzigingen/)).toBeInTheDocument();
    expect(screen.getByText(/Vlam: 95%/)).toBeInTheDocument();
    for (const format of ['HTML', 'CSV', 'PDF']) {
      expect(screen.getByRole('link', { name: new RegExp(format) })).toHaveAttribute(
        'href',
        `/api/reports/day/${format.toLowerCase()}?snapshot_id=snapshot-1`,
      );
    }
  });
});
