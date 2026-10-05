import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { useStatus } from './system.ts';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });
}

describe('API hooks', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete window.__INGRESS_PATH__;
  });

  it('fetches /api/status through the typed client, honouring the ingress base path', async () => {
    window.__INGRESS_PATH__ = '/api/hassio_ingress/abc/';
    const fetchMock = vi.fn<typeof fetch>(() =>
      Promise.resolve(jsonResponse({ stub_data: true, source_text: 'test' })),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useStatus(), { wrapper });
    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.source_text).toBe('test');
    expect((fetchMock.mock.calls[0]?.[0] as Request).url).toContain(
      '/api/hassio_ingress/abc/api/status',
    );
  });

  it('surfaces RFC 7807 problems as ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ title: 'Not implemented', status: 501 }, 501))),
    );
    const { result } = renderHook(() => useStatus(), { wrapper });
    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(result.current.error).toMatchObject({ name: 'ApiError', status: 501 });
  });
});
